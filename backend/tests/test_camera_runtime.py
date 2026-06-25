from pathlib import Path
import time

import numpy as np

from app.camera_runtime import CameraRuntimeConfig, CameraSessionRuntime
from app.machine import SimulationAdapter
from app.models import FrameDetection, MonitoringSession, PPE, SessionMode
from app.monitoring import MonitoringEngine
from app.store import JsonStore


class FakeCapture:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = 0
        self.released = False

    def isOpened(self):
        return True

    def set(self, *_args):
        return True

    def read(self):
        if not self.frames:
            return False, None
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return True, frame.copy()

    def release(self):
        self.released = True


class FakeVision:
    ready = True

    def __init__(self):
        self.calls = 0

    def infer(self, session_id, frame, ppe_items):
        self.calls += 1
        person = FrameDetection(class_name="Person", confidence=0.9, box=[5, 5, 40, 45], track_id="P1")
        helmet = FrameDetection(class_name="Helmet", confidence=0.95, box=[12, 8, 28, 18], track_id="P1", ppe_code="helmet", evidence=1)
        return [person, helmet], {"P1": [helmet]}, 3.0


class FakePosture:
    def infer(self, session_id, frame, detections):
        return [], 0.0


def make_runtime(tmp_path: Path, frames):
    store = JsonStore(tmp_path / "store.json")
    session = MonitoringSession(id="ses_cam", user_id="usr_employee", mode=SessionMode.individual, required_ppe=["helmet"])
    store.upsert("sessions", session)
    engine = MonitoringEngine(store, SimulationAdapter(store))
    vision = FakeVision()
    capture = FakeCapture(frames)
    config = CameraRuntimeConfig(width=64, height=48, target_fps=30, persist_interval_seconds=999, mirror=False)
    runtime = CameraSessionRuntime(
        "ses_cam",
        store,
        engine,
        vision,  # type: ignore[arg-type]
        FakePosture(),  # type: ignore[arg-type]
        config,
        capture_factory=lambda _index: capture,
    )
    return runtime, store, vision, capture


def test_camera_runtime_processes_latest_frame_and_returns_state(tmp_path: Path):
    frames = [np.full((48, 64, 3), value, dtype=np.uint8) for value in (10, 20, 30)]
    runtime, _store, vision, capture = make_runtime(tmp_path, frames)

    runtime.start()
    for _ in range(80):
        result = runtime.latest_result()
        if result:
            break
        time.sleep(0.01)
    runtime.stop()

    assert capture.released is True
    assert vision.calls >= 1
    assert result is not None
    assert result.source == "backend_camera"
    assert result.tracks[0]["track_id"] == "employee"
    assert result.processing_fps is not None


def test_camera_runtime_flushes_dirty_session_on_stop(tmp_path: Path):
    frames = [np.zeros((48, 64, 3), dtype=np.uint8)]
    runtime, store, _vision, _capture = make_runtime(tmp_path, frames)

    runtime.start()
    for _ in range(80):
        if runtime.latest_result():
            break
        time.sleep(0.01)
    runtime.stop()

    saved = store.get("sessions", "ses_cam", MonitoringSession)
    assert saved is not None
    assert saved.tracks
    assert saved.latency_metrics


def test_latest_frame_jpeg_available_before_and_after_processing(tmp_path: Path):
    frames = [np.zeros((48, 64, 3), dtype=np.uint8)]
    runtime, _store, _vision, _capture = make_runtime(tmp_path, frames)

    runtime.start()
    jpeg = None
    for _ in range(80):
        jpeg = runtime.latest_frame_jpeg()
        if jpeg:
            break
        time.sleep(0.01)
    runtime.stop()

    assert jpeg is not None
    assert jpeg.startswith(b"\xff\xd8")
