from datetime import datetime, timezone
from pathlib import Path

from app.machine import ESP32Adapter
from app.models import MonitoringSession, SessionMode
from app.store import JsonStore


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return b'{"bancada":"BLOQUEADA","locked":true}'


def session() -> MonitoringSession:
    return MonitoringSession(
        id="ses_machine",
        user_id="usr_employee",
        mode=SessionMode.individual,
        required_ppe=["helmet"],
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_esp32_adapter_calls_bloquear_and_records_command(tmp_path: Path, monkeypatch):
    called = []

    def fake_urlopen(request, timeout):
        called.append((request.full_url, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.machine.urlopen", fake_urlopen)
    store = JsonStore(tmp_path / "store.json")
    adapter = ESP32Adapter(store, "http://192.168.1.50", timeout_seconds=1.2)

    command = adapter.cut(session(), "missing helmet")

    assert called == [("http://192.168.1.50/bloquear", 1.2)]
    assert command.action == "CUT"
    assert command.result == "esp32_success_http_200"
    assert store.data["machine_commands"][0]["action"] == "CUT"


def test_esp32_adapter_calls_liberar_and_records_reset(tmp_path: Path, monkeypatch):
    called = []

    def fake_urlopen(request, timeout):
        called.append((request.full_url, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.machine.urlopen", fake_urlopen)
    store = JsonStore(tmp_path / "store.json")
    adapter = ESP32Adapter(store, "http://192.168.1.50/")

    command = adapter.reset(session(), "usr_admin")

    assert called[0][0] == "http://192.168.1.50/liberar"
    assert command.action == "RESET"
    assert command.reset_by_user_id == "usr_admin"
