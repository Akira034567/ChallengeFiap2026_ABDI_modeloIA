from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque

from .machine import MachineSafetyPort
from .models import (
    ComplianceSnapshot,
    FrameDetection,
    Infraction,
    MonitoringSession,
    PPE,
    PPECompliance,
    PPEState,
    SafetyEvent,
    SeverityPolicy,
    TrackedPersonSummary,
)
from .store import JsonStore


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TrackRuntime:
    samples: dict[str, Deque[tuple[datetime, int]]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    open_event_id: dict[str, str] = field(default_factory=dict)
    infraction_created: set[str] = field(default_factory=set)
    cut_created: set[str] = field(default_factory=set)


class MonitoringEngine:
    def __init__(
        self,
        store: JsonStore,
        machine: MachineSafetyPort,
        policy: SeverityPolicy | None = None,
    ):
        self.store = store
        self.machine = machine
        self.policy = policy or SeverityPolicy()
        self.runtime: dict[tuple[str, str], TrackRuntime] = {}

    def _runtime(self, session_id: str, track_id: str) -> TrackRuntime:
        key = (session_id, track_id)
        if key not in self.runtime:
            self.runtime[key] = TrackRuntime()
        return self.runtime[key]

    def _ppe_evidence(
        self,
        required_code: str,
        ppe: PPE,
        assigned: list[FrameDetection],
    ) -> int:
        relevant = [item for item in assigned if item.ppe_code == required_code and item.evidence in {-1, 1}]
        if not relevant:
            return -1
        strongest = max(relevant, key=lambda item: (item.confidence, 1 if item.evidence == 1 else 0))
        return int(strongest.evidence or -1)

    def process(
        self,
        session: MonitoringSession,
        track_assignments: dict[str, list[FrameDetection]],
        timestamp: datetime | None = None,
        persist: bool = True,
    ) -> list[dict]:
        timestamp = timestamp or now_utc()
        ppe_by_code = {item.code: item for item in self.store.list("ppe", PPE)}
        output: list[dict] = []
        current_track_ids: list[str] = []

        for raw_track_id, assigned in track_assignments.items():
            track_id = "employee" if session.mode.value == "individual" else raw_track_id
            current_track_ids.append(track_id)
            user_id = session.user_id if session.mode.value == "individual" else None
            summary = session.tracks.get(track_id) or TrackedPersonSummary(
                track_id=track_id, user_id=user_id
            )
            summary.last_seen_at = timestamp
            summary.samples += 1
            runtime = self._runtime(session.id, track_id)
            track_compliant = True

            for code in session.required_ppe:
                ppe = ppe_by_code.get(code)
                if not ppe:
                    continue
                evidence = self._ppe_evidence(code, ppe, assigned)
                samples = runtime.samples[code]
                samples.append((timestamp, evidence))
                cutoff = timestamp - timedelta(seconds=self.policy.window_seconds)
                while samples and samples[0][0] < cutoff:
                    samples.popleft()

                positive = sum(1 for _, value in samples if value == 1)
                ratio = positive / len(samples) if samples else 0
                state = summary.ppe.get(code) or PPECompliance(ppe_code=code)
                previous_state = state.state
                if ratio >= self.policy.present_ratio:
                    proposed = PPEState.present
                elif ratio < self.policy.absent_ratio:
                    proposed = PPEState.absent
                else:
                    proposed = state.state

                if proposed == PPEState.present:
                    if state.recovered_since is None:
                        state.recovered_since = timestamp
                    recovery = (timestamp - state.recovered_since).total_seconds()
                    if previous_state != PPEState.absent or recovery >= self.policy.recovery_seconds:
                        state.state = PPEState.present
                        state.absent_since = None
                        state.severity = 0
                        self._close_event(runtime, code, timestamp)
                        runtime.infraction_created.discard(code)
                        runtime.cut_created.discard(code)
                else:
                    state.recovered_since = None
                    state.state = PPEState.absent
                    if state.absent_since is None:
                        state.absent_since = timestamp
                    duration = (timestamp - state.absent_since).total_seconds()
                    severity = self._severity(duration)
                    if severity > state.severity:
                        state.severity = severity
                        self._record_transition(
                            session, runtime, summary, code, severity, timestamp, duration
                        )

                state.ratio = round(ratio, 3)
                summary.ppe[code] = state
                session.timeline.append(
                    ComplianceSnapshot(
                        timestamp=timestamp,
                        track_id=track_id,
                        user_id=user_id,
                        ppe_code=code,
                        state=state.state,
                        severity=state.severity,
                        ratio=state.ratio,
                    )
                )
                if len(session.timeline) > 5000:
                    session.timeline = session.timeline[-5000:]
                if state.state != PPEState.present:
                    track_compliant = False

            if track_compliant:
                summary.compliant_samples += 1
            session.tracks[track_id] = summary
            output.append(
                {
                    "track_id": track_id,
                    "user_id": user_id,
                    "ppe": {
                        code: compliance.model_dump(mode="json")
                        for code, compliance in summary.ppe.items()
                    },
                    "compliant": track_compliant,
                }
            )

        session.active_track_ids = current_track_ids
        if persist:
            self.store.upsert("sessions", session)
        return output

    def _severity(self, duration: float) -> int:
        if duration >= self.policy.level_3_seconds:
            return 3
        if duration >= self.policy.level_2_seconds:
            return 2
        if duration >= self.policy.level_1_seconds:
            return 1
        return 0

    def _close_event(self, runtime: TrackRuntime, code: str, timestamp: datetime) -> None:
        event_id = runtime.open_event_id.pop(code, None)
        if not event_id:
            return
        event = self.store.get("events", event_id, SafetyEvent)
        if event:
            event.ended_at = timestamp
            event.duration_seconds = (timestamp - event.started_at).total_seconds()
            self.store.upsert("events", event)

    def _record_transition(
        self,
        session: MonitoringSession,
        runtime: TrackRuntime,
        track: TrackedPersonSummary,
        code: str,
        severity: int,
        timestamp: datetime,
        duration: float,
    ) -> None:
        if severity == 0:
            return
        self._close_event(runtime, code, timestamp)
        event = SafetyEvent(
            session_id=session.id,
            track_id=track.track_id,
            user_id=track.user_id,
            ppe_code=code,
            severity=severity,
            started_at=timestamp,
            duration_seconds=duration,
        )
        self.store.upsert("events", event)
        runtime.open_event_id[code] = event.id

        if severity >= 2 and code not in runtime.infraction_created:
            self.store.upsert(
                "infractions",
                Infraction(
                    session_id=session.id,
                    safety_event_id=event.id,
                    user_id=track.user_id,
                    track_id=track.track_id,
                    ppe_code=code,
                ),
            )
            runtime.infraction_created.add(code)

        if severity >= 3 and code not in runtime.cut_created:
            session.machine_locked = True
            self.machine.cut(
                session,
                f"Ausência de {code} por {duration:.1f}s no track {track.track_id}",
            )
            runtime.cut_created.add(code)

    def active_tracks(self, session: MonitoringSession) -> list[TrackedPersonSummary]:
        if not session.tracks:
            return []
        if session.active_track_ids:
            return [
                session.tracks[track_id]
                for track_id in session.active_track_ids
                if track_id in session.tracks
            ]
        latest_seen = max(track.last_seen_at for track in session.tracks.values())
        cutoff = latest_seen - timedelta(seconds=max(4, self.policy.window_seconds * 2))
        return [track for track in session.tracks.values() if track.last_seen_at >= cutoff]

    def all_tracks_compliant(self, session: MonitoringSession) -> bool:
        tracks = self.active_tracks(session)
        if not tracks:
            return False
        return all(
            track.ppe.get(code)
            and (
                track.ppe[code].state == PPEState.present
                or track.ppe[code].ratio >= self.policy.present_ratio
            )
            for track in tracks
            for code in session.required_ppe
        )
