from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .models import FrameDetection, PPE


def iou(a: list[float], b: list[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = max(1, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection)
    return intersection / union


def center(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def containment(inner: list[float], outer: list[float]) -> float:
    x1, y1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    x2, y2 = min(inner[2], outer[2]), min(inner[3], outer[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    inner_area = max(1, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return intersection / inner_area


def normalize_class_name(value: str) -> str:
    return value.strip().lower().replace('_', '-').replace(' ', '-')


@dataclass
class TrackBox:
    track_id: str
    box: list[float]
    missed: int = 0


class SimpleTracker:
    def __init__(self):
        self.tracks: dict[str, TrackBox] = {}
        self.next_id = 1

    def update(self, boxes: list[list[float]]) -> dict[str, list[float]]:
        boxes = sorted(boxes, key=lambda box: center(box)[0])
        available = set(self.tracks)
        result: dict[str, list[float]] = {}
        for box in boxes:
            best_id = None
            best_score = float("inf")
            bx, by = center(box)
            bw, bh = max(1, box[2] - box[0]), max(1, box[3] - box[1])
            for track_id in available:
                previous = self.tracks[track_id].box
                px, py = center(previous)
                pw, ph = max(1, previous[2] - previous[0]), max(1, previous[3] - previous[1])
                overlap = iou(box, previous)
                distance = ((bx - px) / max(bw, pw, 1)) ** 2 + ((by - py) / max(bh, ph, 1)) ** 2
                size_delta = abs(bw - pw) / max(bw, pw, 1) + abs(bh - ph) / max(bh, ph, 1)
                score = distance + size_delta * 0.12 - overlap * 1.4
                if (overlap >= 0.08 or distance <= 0.42) and score < best_score:
                    best_id, best_score = track_id, score
            if best_id is None:
                best_id = f"P{self.next_id}"
                self.next_id += 1
            else:
                available.remove(best_id)
            self.tracks[best_id] = TrackBox(best_id, box)
            result[best_id] = box
        for track_id in available:
            self.tracks[track_id].missed += 1
            if self.tracks[track_id].missed > 20:
                del self.tracks[track_id]
        return result


class VisionService:
    def __init__(self, model_path: Path, confidence: float = 0.5):
        self.model_path = model_path
        self.confidence = confidence
        self.model = None
        self.error: str | None = None
        self.trackers: dict[str, SimpleTracker] = {}

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            config_dir = self.model_path.parents[1] / 'data' / 'ultralytics'
            config_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault('YOLO_CONFIG_DIR', str(config_dir))
            os.environ.setdefault('MPLCONFIGDIR', str(self.model_path.parents[1] / 'data' / 'matplotlib'))
            from ultralytics import YOLO

            if not self.model_path.exists():
                raise FileNotFoundError(f"Modelo não encontrado: {self.model_path}")
            self.model = YOLO(str(self.model_path))
            self.error = None
        except Exception as exc:
            self.error = str(exc)

    @property
    def ready(self) -> bool:
        return self.model is not None

    def decode(self, data_url: str) -> np.ndarray:
        encoded = data_url.split(",", 1)[-1]
        raw = base64.b64decode(encoded)
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Frame JPEG inválido")
        return frame

    def infer(
        self,
        session_id: str,
        frame: np.ndarray,
        ppe_items: list[PPE],
    ) -> tuple[list[FrameDetection], dict[str, list[FrameDetection]], float]:
        if not self.ready:
            raise RuntimeError(self.error or "Modelo indisponível")
        started = time.perf_counter()
        result = self.model(frame, conf=self.confidence, verbose=False)[0]
        inference_ms = (time.perf_counter() - started) * 1000
        by_positive = {normalize_class_name(item.positive_class): item for item in ppe_items}
        by_negative = {normalize_class_name(item.negative_class): item for item in ppe_items}
        detections: list[FrameDetection] = []
        person_boxes: list[list[float]] = []
        ppe_detections: list[FrameDetection] = []

        if result.boxes is not None:
            for box, confidence, class_id in zip(
                result.boxes.xyxy.tolist(),
                result.boxes.conf.tolist(),
                result.boxes.cls.tolist(),
            ):
                class_name = str(self.model.names[int(class_id)])
                detection = FrameDetection(
                    class_name=class_name,
                    confidence=float(confidence),
                    box=[float(value) for value in box],
                )
                normalized_class = normalize_class_name(class_name)
                if normalized_class in by_positive:
                    detection.ppe_code = by_positive[normalized_class].code
                    detection.evidence = 1
                    ppe_detections.append(detection)
                elif normalized_class in by_negative:
                    detection.ppe_code = by_negative[normalized_class].code
                    detection.evidence = -1
                    ppe_detections.append(detection)
                if normalized_class == 'person':
                    person_boxes.append(detection.box)
                detections.append(detection)

        tracker = self.trackers.setdefault(session_id, SimpleTracker())
        tracks = tracker.update(person_boxes)
        if not tracks and ppe_detections:
            height, width = frame.shape[:2]
            tracks = {'P1': [0.0, 0.0, float(width), float(height)]}
        assignments: dict[str, list[FrameDetection]] = {track_id: [] for track_id in tracks}

        for detection in detections:
            if normalize_class_name(detection.class_name) == "person":
                detection.track_id = max(tracks, key=lambda key: iou(detection.box, tracks[key]), default=None)
                continue
            if not detection.ppe_code:
                continue
            best_track = self._associate(detection, tracks)
            if not best_track and len(tracks) == 1:
                best_track = next(iter(tracks))
            if not best_track and detection.evidence == 1 and "P1" in tracks:
                best_track = "P1"
            if best_track:
                detection.track_id = best_track
                assignments[best_track].append(detection)

        return detections, assignments, inference_ms

    def _associate(self, detection: FrameDetection, tracks: dict[str, list[float]]) -> str | None:
        cx, cy = center(detection.box)
        candidates: list[tuple[str, float]] = []
        for track_id, person in tracks.items():
            x1, y1, x2, y2 = person
            width, height = x2 - x1, y2 - y1
            margin_x, margin_y = width * 0.16, height * 0.08
            overlap = containment(detection.box, person)
            if overlap < 0.18 and not (x1 - margin_x <= cx <= x2 + margin_x and y1 - margin_y <= cy <= y2 + margin_y):
                continue

            relative_y = (cy - y1) / max(height, 1)
            allowed = {
                "helmet": relative_y <= 0.45,
                "goggles": relative_y <= 0.50,
                "gloves": 0.18 <= relative_y <= 0.95,
            }.get(detection.ppe_code or "", True)
            if not allowed:
                continue

            if detection.ppe_code in {"helmet", "goggles"}:
                target_x, target_y = (x1 + x2) / 2, y1 + height * 0.22
                y_weight = 1.35
            elif detection.ppe_code == "gloves":
                target_x, target_y = (x1 + x2) / 2, y1 + height * 0.58
                y_weight = 0.8
            else:
                target_x, target_y = center(person)
                y_weight = 1.0

            distance = ((cx - target_x) / max(width, 1)) ** 2 + y_weight * ((cy - target_y) / max(height, 1)) ** 2
            score = distance - overlap * 0.85
            candidates.append((track_id, score))
        return min(candidates, key=lambda item: item[1])[0] if candidates else None








