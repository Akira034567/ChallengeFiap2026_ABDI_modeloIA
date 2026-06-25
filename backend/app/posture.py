
from __future__ import annotations

import math
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import FrameDetection, PostureDetection
from .vision import normalize_class_name


INPUT_SIZE = [192, 256]
BBOX_REAL = (2000, 2000)
FOCAL = [1500, 1500]
MIN_KEYPOINT_CONFIDENCE = 0.35

J = {
    "hip_center": 0,
    "right_hip": 1,
    "right_knee": 2,
    "right_ankle": 3,
    "left_hip": 4,
    "left_knee": 5,
    "left_ankle": 6,
    "spine_low": 7,
    "spine_mid": 8,
    "neck": 9,
    "head": 10,
    "right_shoulder": 11,
    "right_elbow": 12,
    "right_wrist": 13,
    "left_shoulder": 14,
    "left_elbow": 15,
    "left_wrist": 16,
    "spine_top": 17,
}


@dataclass
class CachedPosture:
    created_at: float
    items: list[PostureDetection]
    inference_ms: float = 0.0


def _angle_between(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 1e-9:
        return 0.0
    value = float(np.dot(a, b) / denom)
    return math.degrees(math.acos(max(-1.0, min(1.0, value))))


def ergonomic_score(coords: np.ndarray) -> tuple[float, dict[str, float | str]]:
    coords = coords.astype(float)
    vertical = np.array([0.0, -1.0, 0.0])

    trunk_vec = coords[J["neck"]] - coords[J["hip_center"]]
    neck_vec = coords[J["head"]] - coords[J["neck"]]
    left_femur = coords[J["left_knee"]] - coords[J["left_hip"]]
    right_femur = coords[J["right_knee"]] - coords[J["right_hip"]]

    femur_angle = (_angle_between(left_femur, vertical) + _angle_between(right_femur, vertical)) / 2.0
    seated = femur_angle > 45.0

    trunk_angle = _angle_between(trunk_vec, vertical)
    if trunk_angle <= 15.0:
        trunk_penalty = 0.0
    elif trunk_angle <= 30.0:
        trunk_penalty = ((trunk_angle - 15.0) / 15.0) * 20.0
    elif trunk_angle <= 60.0:
        trunk_penalty = 20.0 + ((trunk_angle - 30.0) / 30.0) * 40.0
    else:
        trunk_penalty = 60.0 + (min(trunk_angle - 60.0, 30.0) / 30.0) * 40.0

    if seated:
        left_knee_angle = _angle_between(coords[J["left_ankle"]] - coords[J["left_knee"]], -left_femur)
        right_knee_angle = _angle_between(coords[J["right_ankle"]] - coords[J["right_knee"]], -right_femur)
        knee_deviation = (abs(left_knee_angle - 90.0) + abs(right_knee_angle - 90.0)) / 2.0
        if knee_deviation > 40.0:
            trunk_penalty = min(100.0, trunk_penalty + 10.0)

    neck_angle = _angle_between(neck_vec, vertical)
    if neck_angle <= 20.0:
        neck_penalty = 0.0
    elif neck_angle <= 40.0:
        neck_penalty = ((neck_angle - 20.0) / 20.0) * 25.0
    else:
        neck_penalty = 25.0 + (min(neck_angle - 40.0, 30.0) / 30.0) * 75.0

    shoulder_vec = coords[J["left_shoulder"]] - coords[J["right_shoulder"]]
    shoulder_dist = np.linalg.norm(shoulder_vec[:2]) + 1e-6
    shoulder_delta = abs(coords[J["left_shoulder"]][1] - coords[J["right_shoulder"]][1])
    shoulder_ratio = shoulder_delta / shoulder_dist
    shoulder_penalty = 0.0 if shoulder_ratio < 0.06 else min((shoulder_ratio - 0.06) / 0.14, 1.0) * 100.0

    hip_vec = coords[J["left_hip"]] - coords[J["right_hip"]]
    hip_dist = np.linalg.norm(hip_vec[:2]) + 1e-6
    hip_delta = abs(coords[J["left_hip"]][1] - coords[J["right_hip"]][1])
    hip_ratio = hip_delta / hip_dist
    hip_limit = 0.10 if seated else 0.06
    hip_penalty = 0.0 if hip_ratio < hip_limit else min((hip_ratio - hip_limit) / 0.14, 1.0) * 100.0

    left_arm = coords[J["left_elbow"]] - coords[J["left_shoulder"]]
    right_arm = coords[J["right_elbow"]] - coords[J["right_shoulder"]]
    left_arm_raise = _angle_between(left_arm, vertical)
    right_arm_raise = _angle_between(right_arm, vertical)
    shoulder_raise = (max(0.0, left_arm_raise - 60.0) + max(0.0, right_arm_raise - 60.0)) / 2.0
    shoulder_raise_penalty = min(shoulder_raise / 45.0, 1.0) * 40.0

    score = 100.0 - (
        trunk_penalty * 0.40
        + neck_penalty * 0.20
        + shoulder_penalty * 0.10
        + hip_penalty * 0.15
        + shoulder_raise_penalty * 0.15
    )
    return max(0.0, min(100.0, float(score))), {
        "trunk": float(trunk_penalty),
        "neck": float(neck_penalty),
        "shoulders": float(shoulder_penalty),
        "hips": float(hip_penalty),
        "raised_shoulders": float(shoulder_raise_penalty),
        "posture_mode": "Sentado" if seated else "Em pe",
    }


def posture_advice(penalties: dict[str, float | str]) -> list[str]:
    labels = {
        "trunk": "Reduza a inclinacao do tronco e aproxime o corpo da tarefa.",
        "neck": "Mantenha o pescoco mais neutro; eleve ou aproxime o ponto de foco.",
        "shoulders": "Alinhe melhor os ombros e evite torcao lateral.",
        "hips": "Distribua o peso entre os dois lados do corpo e alinhe o quadril.",
        "raised_shoulders": "Evite manter os bracos elevados; ajuste a altura da tarefa.",
    }
    numeric = [
        (key, float(value))
        for key, value in penalties.items()
        if key in labels and isinstance(value, (int, float)) and float(value) >= 18.0
    ]
    numeric.sort(key=lambda item: item[1], reverse=True)
    return [labels[key] for key, _ in numeric[:3]] or ["Postura dentro da faixa esperada; mantenha estabilidade e movimentos suaves."]


def compact_keypoints(joints: np.ndarray) -> list[list[float]]:
    selected = joints[:18].astype(float)
    return [[round(float(value), 4) for value in point] for point in selected]


def compact_keypoints_2d(joints: np.ndarray, scores: np.ndarray) -> list[list[float]]:
    selected = joints[:18].astype(float)
    selected_scores = scores[:18].reshape(-1)
    return [
        [round(float(point[0]), 2), round(float(point[1]), 2), round(float(score), 3)]
        for point, score in zip(selected, selected_scores)
    ]


def classify_posture(reba_score: float, score: float) -> tuple[str, int]:
    if reba_score >= 7 or score < 55:
        return "inapto", 2
    if reba_score >= 5 or score < 70:
        return "atencao", 1
    return "apto", 0


class PostureService:
    def __init__(self, model_path: Path, enabled: bool = True, interval_seconds: float = 1.0):
        self.model_path = model_path
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self.model = None
        self.device = None
        self.error: str | None = None
        self.cache: dict[str, CachedPosture] = {}
        self.running: dict[str, Future[CachedPosture]] = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="posture")

    def load(self) -> None:
        if not self.enabled:
            self.error = "Deteccao de postura desativada"
            return
        if self.model is not None:
            return
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Modelo de postura nao encontrado: {self.model_path}")
            os.environ.setdefault("MPLCONFIGDIR", str(self.model_path.parents[1] / "data" / "matplotlib"))
            import torch

            from .posture_mp3d.models.res50_mobilenetv2_rle import Res50_Mobilenetv2_RLE

            self.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
            model = Res50_Mobilenetv2_RLE()
            state = torch.load(str(self.model_path), map_location=self.device, weights_only=True)
            model.load_state_dict(state, strict=False)
            model.to(self.device).eval()
            self.model = model
            self.error = None
        except Exception as exc:
            self.model = None
            self.error = str(exc)

    @property
    def ready(self) -> bool:
        return self.model is not None

    def infer(
        self,
        session_id: str,
        frame: np.ndarray,
        detections: list[FrameDetection],
    ) -> tuple[list[PostureDetection], float]:
        now = time.time()
        completed = self._collect_completed(session_id)
        cached = self.cache.get(session_id)
        if completed:
            cached = completed

        if not self.ready:
            return cached.items if cached else [], 0.0

        due = cached is None or now - cached.created_at >= self.interval_seconds
        if due and session_id not in self.running:
            person_detections = [
                item.model_copy(deep=True)
                for item in detections
                if normalize_class_name(item.class_name) == "person" and item.track_id
            ]
            if person_detections:
                self.running[session_id] = self.executor.submit(
                    self._infer_now,
                    frame.copy(),
                    person_detections,
                )
            else:
                empty = CachedPosture(now, [], 0.0)
                self.cache[session_id] = empty
                return [], 0.0

        if completed:
            return completed.items, completed.inference_ms
        return cached.items if cached else [], 0.0

    def _collect_completed(self, session_id: str) -> CachedPosture | None:
        future = self.running.get(session_id)
        if not future or not future.done():
            return None
        self.running.pop(session_id, None)
        try:
            result = future.result()
        except Exception as exc:
            self.error = str(exc)
            return None
        self.cache[session_id] = result
        return result

    def _infer_now(
        self,
        frame: np.ndarray,
        person_detections: list[FrameDetection],
    ) -> CachedPosture:
        if not self.ready or not person_detections:
            return CachedPosture(time.time(), [], 0.0)

        import torch
        from .posture_mp3d.utils.REBA import REBA
        from .posture_mp3d.utils.transform import ProcessBox, pre2coord

        started = time.perf_counter()
        img_batch = []
        k_batch = []
        meta: list[tuple[FrameDetection, list[float]]] = []
        for person in person_detections:
            box = person.box
            crop, bbox = ProcessBox(box, frame, INPUT_SIZE)
            k_value = np.array([
                math.sqrt(BBOX_REAL[0] * BBOX_REAL[1] * FOCAL[0] * FOCAL[1] / max(1.0, bbox[2] * bbox[3]))
            ], dtype=np.float32)
            img_batch.append(crop)
            k_batch.append(torch.FloatTensor(k_value))
            meta.append((person, bbox))

        if not img_batch:
            return CachedPosture(time.time(), [], 0.0)

        with torch.no_grad():
            output = self.model(torch.stack(img_batch).to(self.device), torch.stack(k_batch).to(self.device))

        joints_batch = output.pred_jts.detach().cpu().numpy()
        confidence_batch = output.maxvals.detach().cpu().numpy()
        items: list[PostureDetection] = []
        for index, (person, _) in enumerate(meta):
            confidence = float(np.mean(confidence_batch[index]))
            if confidence < MIN_KEYPOINT_CONFIDENCE:
                continue
            joints = joints_batch[index]
            _, bbox = meta[index]
            joints_2d = pre2coord(joints, INPUT_SIZE, bbox, output_3d=True)
            _, reba_score = REBA(joints)
            ergo_score, penalties = ergonomic_score(joints)
            state, severity = classify_posture(float(reba_score), ergo_score)
            numeric_penalties = {key: value for key, value in penalties.items() if isinstance(value, (int, float))}
            items.append(
                PostureDetection(
                    track_id=str(person.track_id),
                    box=person.box,
                    reba_score=float(reba_score),
                    ergonomic_score=round(ergo_score, 2),
                    state=state,
                    severity=severity,
                    confidence=round(confidence, 3),
                    posture_mode=str(penalties.get("posture_mode", "N/A")),
                    penalties=numeric_penalties,
                    advice=posture_advice(penalties),
                    keypoints_3d=compact_keypoints(joints),
                    keypoints_2d=compact_keypoints_2d(joints_2d, confidence_batch[index]),
                )
            )
        inference_ms = (time.perf_counter() - started) * 1000
        return CachedPosture(time.time(), items, inference_ms)
