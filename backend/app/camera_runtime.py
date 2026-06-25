from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator

import cv2
import numpy as np

from .models import FrameResult, LatencyMetric, MonitoringSession, PPE, PostureSnapshot, SessionStatus
from .monitoring import MonitoringEngine
from .posture import PostureService
from .store import JsonStore
from .vision import VisionService


@dataclass
class CameraRuntimeConfig:
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    target_fps: float = 10.0
    persist_interval_seconds: float = 3.0
    jpeg_quality: int = 78
    mirror: bool = True

    @classmethod
    def from_env(cls) -> "CameraRuntimeConfig":
        return cls(
            camera_index=int(os.getenv("CAMERA_INDEX", "0")),
            width=int(os.getenv("CAMERA_WIDTH", "1280")),
            height=int(os.getenv("CAMERA_HEIGHT", "720")),
            target_fps=float(os.getenv("EPI_TARGET_FPS", "10")),
            persist_interval_seconds=float(os.getenv("SESSION_PERSIST_INTERVAL_SECONDS", "3")),
            jpeg_quality=int(os.getenv("MJPEG_JPEG_QUALITY", "78")),
            mirror=os.getenv("CAMERA_MIRROR", "1").strip().lower() not in {"0", "false", "no"},
        )


class CameraSessionRuntime:
    def __init__(
        self,
        session_id: str,
        store: JsonStore,
        engine: MonitoringEngine,
        vision: VisionService,
        posture: PostureService,
        config: CameraRuntimeConfig,
        capture_factory: Callable[[int], object] | None = None,
    ):
        self.session_id = session_id
        self.store = store
        self.engine = engine
        self.vision = vision
        self.posture = posture
        self.config = config
        self.capture_factory = capture_factory or cv2.VideoCapture
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._process_thread: threading.Thread | None = None
        self._capture = None
        self._latest_frame: np.ndarray | None = None
        self._latest_frame_version = 0
        self._processed_frame_version = -1
        self._latest_result: FrameResult | None = None
        self._latest_jpeg: bytes | None = None
        self._last_persist_at = 0.0
        self._last_error: str | None = None
        self._dirty_session: MonitoringSession | None = None
        self._started_at = 0.0
        self._processed_count = 0
        self._camera_count = 0

    @property
    def running(self) -> bool:
        return self._capture_thread is not None and self._capture_thread.is_alive() and not self._stop.is_set()

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._last_error

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._last_error = None
        self._started_at = time.perf_counter()
        self._processed_count = 0
        self._camera_count = 0
        capture = self.capture_factory(self.config.camera_index)
        if hasattr(capture, "set"):
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        if hasattr(capture, "isOpened") and not capture.isOpened():
            if hasattr(capture, "release"):
                capture.release()
            raise RuntimeError(f"Camera {self.config.camera_index} indisponivel")
        self._capture = capture
        self._capture_thread = threading.Thread(target=self._capture_loop, name=f"camera-capture-{self.session_id}", daemon=True)
        self._process_thread = threading.Thread(target=self._process_loop, name=f"camera-process-{self.session_id}", daemon=True)
        self._capture_thread.start()
        self._process_thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in (self._capture_thread, self._process_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        capture = self._capture
        self._capture = None
        if capture is not None and hasattr(capture, "release"):
            capture.release()
        self.flush()

    def flush(self) -> None:
        with self._lock:
            session = self._dirty_session
            self._dirty_session = None
        if session:
            self.store.upsert("sessions", session)

    def latest_result(self) -> FrameResult | None:
        with self._lock:
            return self._latest_result.model_copy(deep=True) if self._latest_result else None

    def latest_frame_jpeg(self) -> bytes | None:
        with self._lock:
            if self._latest_frame is None:
                return self._latest_jpeg
            frame = self._latest_frame.copy()
            result = self._latest_result.model_copy(deep=True) if self._latest_result else None
        annotated = self._draw_overlay(frame, result)
        ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality])
        if not ok:
            return None
        jpeg = encoded.tobytes()
        with self._lock:
            self._latest_jpeg = jpeg
        return jpeg

    def stream(self, interval_seconds: float = 1 / 24) -> Iterator[bytes]:
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-cache\r\n\r\n"
        while not self._stop.is_set():
            jpeg = self.latest_frame_jpeg()
            if jpeg:
                yield boundary + jpeg + b"\r\n"
            time.sleep(interval_seconds)

    def _capture_loop(self) -> None:
        capture = self._capture
        while not self._stop.is_set() and capture is not None:
            ok, frame = capture.read()
            if not ok or frame is None:
                with self._lock:
                    self._last_error = "Falha ao ler frame da camera"
                time.sleep(0.05)
                continue
            if self.config.mirror:
                frame = cv2.flip(frame, 1)
            with self._lock:
                self._latest_frame = frame
                self._latest_frame_version += 1
                self._camera_count += 1

    def _process_loop(self) -> None:
        interval = 1.0 / max(self.config.target_fps, 1.0)
        while not self._stop.is_set():
            started = time.perf_counter()
            with self._lock:
                frame = self._latest_frame.copy() if self._latest_frame is not None else None
                version = self._latest_frame_version
            if frame is not None and version != self._processed_frame_version:
                try:
                    self._process_frame(frame, version)
                except Exception as exc:
                    with self._lock:
                        self._last_error = str(exc)
            elapsed = time.perf_counter() - started
            time.sleep(max(0.0, interval - elapsed))

    def _process_frame(self, frame: np.ndarray, version: int) -> None:
        session = self.store.get("sessions", self.session_id, MonitoringSession)
        if not session or session.status != SessionStatus.active:
            self._stop.set()
            return

        received_at_ms = time.time() * 1000
        processing_started = time.perf_counter()
        frame_id = str(int(received_at_ms))
        ppe_items = [ppe for ppe in self.store.list("ppe", PPE) if ppe.code in session.required_ppe]
        detections, assignments, ppe_inference_ms = self.vision.infer(session.id, frame, ppe_items)
        posture_items, posture_inference_ms = self.posture.infer(session.id, frame, detections)
        if session.mode.value == "individual":
            for item in posture_items:
                item.track_id = "employee"
        if posture_items and posture_inference_ms > 0:
            captured_at = datetime.now(timezone.utc)
            session.posture_timeline.extend(
                PostureSnapshot(
                    timestamp=captured_at,
                    track_id=item.track_id if session.mode.value == "group" else "employee",
                    state=item.state,
                    severity=item.severity,
                    reba_score=item.reba_score,
                    ergonomic_score=item.ergonomic_score,
                    confidence=item.confidence,
                    posture_mode=item.posture_mode,
                    penalties=item.penalties,
                    advice=item.advice,
                    keypoints_3d=item.keypoints_3d,
                    keypoints_2d=item.keypoints_2d,
                )
                for item in posture_items
            )
            session.posture_timeline = session.posture_timeline[-5000:]

        machine_locked_before = session.machine_locked
        inference_ms = ppe_inference_ms + posture_inference_ms
        tracks = self.engine.process(session, assignments, persist=False)
        processing_ms = (time.perf_counter() - processing_started) * 1000 - inference_ms
        server_total_ms = (time.time() * 1000) - received_at_ms
        session.latency_metrics.append(
            LatencyMetric(
                frame_id=frame_id,
                captured_at_ms=received_at_ms,
                received_at_ms=received_at_ms,
                inference_ms=inference_ms,
                processing_ms=max(0, processing_ms),
                server_total_ms=server_total_ms,
            )
        )
        session.latency_metrics = session.latency_metrics[-500:]
        now = time.perf_counter()
        should_persist = session.machine_locked != machine_locked_before or now - self._last_persist_at >= self.config.persist_interval_seconds
        if should_persist:
            self.store.upsert("sessions", session)
            self._last_persist_at = now

        result = FrameResult(
            frame_id=frame_id,
            image_width=int(frame.shape[1]),
            image_height=int(frame.shape[0]),
            detections=detections,
            tracks=tracks,
            posture=posture_items,
            machine_locked=session.machine_locked,
            inference_ms=inference_ms,
            processing_ms=max(0, processing_ms),
            server_total_ms=server_total_ms,
            server_sent_at_ms=time.time() * 1000,
            source="backend_camera",
            frame_age_ms=0.0,
            camera_fps=self._rate(self._camera_count),
            processing_fps=self._rate(self._processed_count + 1),
        )
        with self._lock:
            self._latest_result = result
            self._dirty_session = None if should_persist else session
            self._processed_frame_version = version
            self._processed_count += 1
            self._last_error = None

    def _rate(self, count: int) -> float:
        elapsed = max(0.001, time.perf_counter() - self._started_at)
        return round(count / elapsed, 2)

    def _draw_overlay(self, frame: np.ndarray, result: FrameResult | None) -> np.ndarray:
        if result is None:
            return frame
        sx = frame.shape[1] / max(result.image_width, 1)
        sy = frame.shape[0] / max(result.image_height, 1)
        for detection in result.detections:
            x1, y1, x2, y2 = [int(v) for v in detection.box]
            is_person = detection.class_name.lower() == "person"
            color = (248, 189, 56) if is_person else (68, 68, 239) if detection.evidence == -1 else (85, 197, 34)
            pt1 = (int(x1 * sx), int(y1 * sy))
            pt2 = (int(x2 * sx), int(y2 * sy))
            cv2.rectangle(frame, pt1, pt2, color, 3 if is_person else 2)
            label = f"{detection.track_id or ''} {detection.class_name} {detection.confidence * 100:.0f}%".strip()
            cv2.putText(frame, label, (pt1[0] + 4, max(18, pt1[1] + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)
        for item in result.posture:
            color = (68, 68, 239) if item.severity >= 2 else (11, 158, 245) if item.severity == 1 else (250, 139, 167)
            points = item.keypoints_2d or []
            for a, b in BACKEND_POSE_CONNECTIONS:
                if a >= len(points) or b >= len(points):
                    continue
                pa, pb = points[a], points[b]
                if len(pa) < 3 or len(pb) < 3 or pa[2] < 0.35 or pb[2] < 0.35:
                    continue
                cv2.line(frame, (int(pa[0] * sx), int(pa[1] * sy)), (int(pb[0] * sx), int(pb[1] * sy)), color, 3, cv2.LINE_AA)
            for point in points:
                if len(point) < 3 or point[2] < 0.35:
                    continue
                center = (int(point[0] * sx), int(point[1] * sy))
                cv2.circle(frame, center, 5, (2, 8, 23), -1, cv2.LINE_AA)
                cv2.circle(frame, center, 3, color, -1, cv2.LINE_AA)
            x1, y1, x2, _ = [int(v) for v in item.box]
            label = f"Postura {item.track_id}: {item.state.upper()} REBA {item.reba_score:.0f} {item.ergonomic_score:.0f}/100"
            origin = (int(x1 * sx), max(24, int(y1 * sy) - 8))
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(frame, (origin[0], origin[1] - th - 8), (origin[0] + tw + 10, origin[1] + 5), (2, 8, 23), -1)
            cv2.putText(frame, label, (origin[0] + 5, origin[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
        return frame


BACKEND_POSE_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3),
    (0, 4), (4, 5), (5, 6),
    (0, 7), (7, 8), (8, 9), (9, 10),
    (9, 11), (11, 12), (12, 13),
    (9, 14), (14, 15), (15, 16),
    (8, 17),
)


class CameraRuntimeManager:
    def __init__(
        self,
        store: JsonStore,
        engine: MonitoringEngine,
        vision: VisionService,
        posture: PostureService,
        config: CameraRuntimeConfig | None = None,
        capture_factory: Callable[[int], object] | None = None,
    ):
        self.store = store
        self.engine = engine
        self.vision = vision
        self.posture = posture
        self.config = config or CameraRuntimeConfig.from_env()
        self.capture_factory = capture_factory
        self._lock = threading.RLock()
        self._runtimes: dict[str, CameraSessionRuntime] = {}

    def start(self, session_id: str) -> CameraSessionRuntime:
        with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime and runtime.running:
                return runtime
            runtime = CameraSessionRuntime(
                session_id,
                self.store,
                self.engine,
                self.vision,
                self.posture,
                self.config,
                self.capture_factory,
            )
            self._runtimes[session_id] = runtime
        runtime.start()
        return runtime

    def get(self, session_id: str) -> CameraSessionRuntime | None:
        with self._lock:
            return self._runtimes.get(session_id)

    def stop(self, session_id: str) -> None:
        with self._lock:
            runtime = self._runtimes.pop(session_id, None)
        if runtime:
            runtime.stop()

    def stop_all(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.stop()
