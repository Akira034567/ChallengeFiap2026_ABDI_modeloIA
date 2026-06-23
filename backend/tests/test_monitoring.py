from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.machine import SimulationAdapter
from app.models import FrameDetection, MonitoringSession, SessionMode
from app.monitoring import MonitoringEngine
from app.store import JsonStore


def detection(code: str, evidence: int) -> FrameDetection:
    return FrameDetection(
        class_name="Helmet" if evidence == 1 else "No-Helmet",
        confidence=0.9,
        box=[0, 0, 10, 10],
        track_id="P1",
        ppe_code=code,
        evidence=evidence,
    )


def test_monitoring_records_infraction_and_cut(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    machine = SimulationAdapter(store)
    engine = MonitoringEngine(store, machine)
    session = MonitoringSession(
        id="ses_test",
        user_id="usr_employee",
        mode=SessionMode.individual,
        required_ppe=["helmet"],
    )
    store.upsert("sessions", session)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for seconds in (0, 2, 5, 10):
        engine.process(session, {"P1": [detection("helmet", -1)]}, start + timedelta(seconds=seconds))

    events = store.data["events"]
    infractions = store.data["infractions"]
    commands = store.data["machine_commands"]

    assert any(event["severity"] == 1 for event in events)
    assert any(event["severity"] == 2 for event in events)
    assert any(event["severity"] == 3 for event in events)
    assert len(infractions) == 1
    assert any(command["action"] == "CUT" for command in commands)
    assert session.machine_locked is True


def test_monitoring_recovers_after_stable_presence(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    engine = MonitoringEngine(store, SimulationAdapter(store))
    session = MonitoringSession(
        id="ses_recovery",
        user_id="usr_employee",
        mode=SessionMode.group,
        required_ppe=["helmet"],
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    engine.process(session, {"P1": [detection("helmet", -1)]}, start)
    engine.process(session, {"P1": [detection("helmet", -1)]}, start + timedelta(seconds=2))
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=5))
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=8))
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=9))
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=11))

    assert session.tracks["P1"].ppe["helmet"].state == "present"
    assert session.tracks["P1"].ppe["helmet"].severity == 0

def test_reset_compliance_ignores_stale_group_tracks(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    engine = MonitoringEngine(store, SimulationAdapter(store))
    session = MonitoringSession(
        id="ses_group_reset",
        user_id="usr_employee",
        mode=SessionMode.group,
        required_ppe=["helmet"],
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    engine.process(session, {"P1": [detection("helmet", -1)]}, start)
    engine.process(session, {"P2": [detection("helmet", 1)]}, start + timedelta(seconds=10))
    engine.process(session, {"P2": [detection("helmet", 1)]}, start + timedelta(seconds=11))
    engine.process(session, {"P2": [detection("helmet", 1)]}, start + timedelta(seconds=12))

    assert session.tracks["P1"].ppe["helmet"].state.value == "absent"
    assert session.tracks["P2"].ppe["helmet"].state.value == "present"
    assert engine.all_tracks_compliant(session) is True


def test_positive_evidence_can_beat_weaker_negative_for_same_track(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    engine = MonitoringEngine(store, SimulationAdapter(store))
    session = MonitoringSession(
        id="ses_conflicting_evidence",
        user_id="usr_employee",
        mode=SessionMode.group,
        required_ppe=["helmet"],
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    negative = detection("helmet", -1)
    negative.confidence = 0.55
    positive = detection("helmet", 1)
    positive.confidence = 0.91

    for second in (0, 1, 2):
        engine.process(session, {"P1": [negative, positive]}, start + timedelta(seconds=second))

    assert session.tracks["P1"].ppe["helmet"].state.value == "present"

def test_reset_compliance_accepts_recent_positive_ratio(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    engine = MonitoringEngine(store, SimulationAdapter(store))
    session = MonitoringSession(
        id="ses_ratio_reset",
        user_id="usr_employee",
        mode=SessionMode.group,
        required_ppe=["helmet"],
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    engine.process(session, {"P1": [detection("helmet", -1)]}, start)
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=1))
    engine.process(session, {"P1": [detection("helmet", 1)]}, start + timedelta(seconds=2))

    assert session.tracks["P1"].ppe["helmet"].ratio >= 0.6
    assert engine.all_tracks_compliant(session) is True
