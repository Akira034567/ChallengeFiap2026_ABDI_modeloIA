from __future__ import annotations

from abc import ABC, abstractmethod

from .models import MachineCommand, MonitoringSession
from .store import JsonStore


class MachineSafetyPort(ABC):
    @abstractmethod
    def cut(self, session: MonitoringSession, reason: str) -> MachineCommand:
        raise NotImplementedError

    @abstractmethod
    def reset(self, session: MonitoringSession, user_id: str) -> MachineCommand:
        raise NotImplementedError


class SimulationAdapter(MachineSafetyPort):
    def __init__(self, store: JsonStore):
        self.store = store

    def cut(self, session: MonitoringSession, reason: str) -> MachineCommand:
        command = MachineCommand(
            session_id=session.id,
            action="CUT",
            reason=reason,
            result="simulated_success",
        )
        self.store.upsert("machine_commands", command)
        return command

    def reset(self, session: MonitoringSession, user_id: str) -> MachineCommand:
        command = MachineCommand(
            session_id=session.id,
            action="RESET",
            reason="Reset manual após recuperação da conformidade",
            result="simulated_success",
            reset_by_user_id=user_id,
        )
        self.store.upsert("machine_commands", command)
        return command


class ESP32Adapter(MachineSafetyPort):
    """Extension point for the future Wi-Fi integration."""

    def cut(self, session: MonitoringSession, reason: str) -> MachineCommand:
        raise NotImplementedError("Configure the ESP32 transport before enabling this adapter")

    def reset(self, session: MonitoringSession, user_id: str) -> MachineCommand:
        raise NotImplementedError("Configure the ESP32 transport before enabling this adapter")



