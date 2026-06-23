from pathlib import Path

import numpy as np

from app.models import PPE
from app.vision import VisionService


class Values:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class Boxes:
    def __init__(self, boxes, confidences, classes):
        self.xyxy = Values(boxes)
        self.conf = Values(confidences)
        self.cls = Values(classes)


class Result:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeModel:
    names = {0: "Helmet", 1: "Person", 2: "Goggles", 3: "No-Goggles"}

    def __init__(self, boxes):
        self._boxes = boxes

    def __call__(self, frame, conf, verbose):
        return [Result(self._boxes)]


def test_vision_creates_synthetic_track_when_ppe_exists_without_person():
    service = VisionService(Path("missing.pt"))
    service.model = FakeModel(Boxes([[20, 10, 60, 40]], [0.92], [0]))
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    ppe = [PPE(code="helmet", name="Capacete", positive_class="Helmet", negative_class="No-Helmet")]

    detections, assignments, _ = service.infer("ses", frame, ppe)

    assert "P1" in assignments
    assert assignments["P1"][0].ppe_code == "helmet"
    assert detections[0].track_id == "P1"


def test_vision_assigns_to_single_person_even_when_region_is_strict():
    service = VisionService(Path("missing.pt"))
    service.model = FakeModel(
        Boxes(
            [[20, 20, 80, 80], [0, 0, 10, 10]],
            [0.95, 0.91],
            [1, 0],
        )
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    ppe = [PPE(code="helmet", name="Capacete", positive_class="Helmet", negative_class="No-Helmet")]

    detections, assignments, _ = service.infer("ses", frame, ppe)

    track_id = next(iter(assignments))
    assert assignments[track_id][0].ppe_code == "helmet"
    assert detections[1].track_id == track_id

def test_vision_assigns_goggles_to_nearest_head_region_with_two_people():
    service = VisionService(Path("missing.pt"))
    service.model = FakeModel(
        Boxes(
            [
                [10, 10, 90, 190],
                [110, 10, 190, 190],
                [130, 38, 170, 62],
            ],
            [0.95, 0.95, 0.92],
            [1, 1, 2],
        )
    )
    frame = np.zeros((220, 220, 3), dtype=np.uint8)
    ppe = [PPE(code="goggles", name="\u00d3culos", positive_class="Goggles", negative_class="No-Goggles")]

    detections, assignments, _ = service.infer("ses_two_people", frame, ppe)

    assert "P1" in assignments
    assert "P2" in assignments
    assert len(assignments["P1"]) == 0
    assert assignments["P2"][0].ppe_code == "goggles"
    assert assignments["P2"][0].evidence == 1


def test_vision_assigns_negative_goggles_to_correct_person_only():
    service = VisionService(Path("missing.pt"))
    service.model = FakeModel(
        Boxes(
            [
                [10, 10, 90, 190],
                [110, 10, 190, 190],
                [130, 38, 170, 62],
            ],
            [0.95, 0.95, 0.92],
            [1, 1, 3],
        )
    )
    frame = np.zeros((220, 220, 3), dtype=np.uint8)
    ppe = [PPE(code="goggles", name="\u00d3culos", positive_class="Goggles", negative_class="No-Goggles")]

    _, assignments, _ = service.infer("ses_two_people_negative", frame, ppe)

    assert len(assignments["P1"]) == 0
    assert assignments["P2"][0].ppe_code == "goggles"
    assert assignments["P2"][0].evidence == -1
