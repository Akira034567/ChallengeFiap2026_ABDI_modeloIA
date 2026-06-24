from __future__ import annotations

import json
from abc import ABC, abstractmethod
from urllib.error import URLError
from urllib.request import Request, urlopen

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
    def __init__(self, store: JsonStore, base_url: str, timeout_seconds: float = 2.5):
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def cut(self, session: MonitoringSession, reason: str) -> MachineCommand:
        result = self._call("/bloquear")
        command = MachineCommand(
            session_id=session.id,
            action="CUT",
            reason=reason,
            result=result,
        )
        self.store.upsert("machine_commands", command)
        return command

    def reset(self, session: MonitoringSession, user_id: str) -> MachineCommand:
        result = self._call("/liberar")
        command = MachineCommand(
            session_id=session.id,
            action="RESET",
            reason="Reset manual após recuperação da conformidade",
            result=result,
            reset_by_user_id=user_id,
        )
        self.store.upsert("machine_commands", command)
        return command

    def status(self) -> str:
        return self._call("/status")

    def _call(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(512).decode("utf-8", errors="replace").strip()
                if response.status >= 400:
                    return f"esp32_http_{response.status}: {body}"
                if path == "/status":
                    try:
                        parsed = json.loads(body)
                        return f"esp32_status_{parsed.get('bancada', body)}"
                    except json.JSONDecodeError:
                        return f"esp32_status_{body or response.status}"
                return f"esp32_success_http_{response.status}"
        except TimeoutError:
            return "esp32_error_timeout"
        except URLError as exc:
            return f"esp32_error_{exc.reason}"
        except OSError as exc:
            return f"esp32_error_{exc}"
