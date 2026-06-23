from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .models import Area, JobRole, PPE, Preset, User, UserRole
from .security import hash_password

T = TypeVar("T", bound=BaseModel)


class JsonStore:
    collections = (
        "users",
        "ppe",
        "presets",
        "job_roles",
        "areas",
        "sessions",
        "events",
        "infractions",
        "machine_commands",
        "reports",
    )

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.data = self._load()
        repaired = self._repair_mojibake(self.data)
        self._seed()
        if repaired:
            self._write()

    def _empty(self) -> dict[str, list[dict[str, Any]]]:
        return {name: [] for name in self.collections}

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return self._empty()
        with self.path.open("r", encoding="utf-8-sig") as handle:
            loaded = json.load(handle)
        for name in self.collections:
            loaded.setdefault(name, [])
        return loaded

    def _repair_mojibake(self, value: Any) -> bool:
        changed, repaired = self._repair_value(value)
        if changed and isinstance(repaired, dict):
            value.clear()
            value.update(repaired)
        return changed

    def _repair_value(self, value: Any) -> tuple[bool, Any]:
        if isinstance(value, str):
            repaired = self._repair_text(value)
            return repaired != value, repaired
        if isinstance(value, list):
            changed = False
            items = []
            for item in value:
                item_changed, repaired_item = self._repair_value(item)
                changed = changed or item_changed
                items.append(repaired_item)
            return changed, items
        if isinstance(value, dict):
            changed = False
            items = {}
            for key, item in value.items():
                item_changed, repaired_item = self._repair_value(item)
                changed = changed or item_changed
                items[key] = repaired_item
            return changed, items
        return False, value

    def _repair_text(self, value: str) -> str:
        markers = ("\u00c3", "\u00c2", "\ufffd", "\u00e2\u20ac", "\u00e2\u20ac\u0153", "\u00e2\u20ac\u009d", "\u00e2\u20ac\u00a2", "\u00e2\u20ac\u201d", "\u00e2\u20ac\u201c", "\u00e2\u201e\u00a2", "\u00e2\u0153", "\u00e2\u201d")
        repaired = value
        for _ in range(3):
            if not any(marker in repaired for marker in markers):
                break
            try:
                candidate = repaired.encode("cp1252").decode("utf-8")
            except UnicodeError:
                try:
                    candidate = repaired.encode("latin-1").decode("utf-8")
                except UnicodeError:
                    break
            if candidate == repaired:
                break
            repaired = candidate
        return repaired

    def _write(self) -> None:
        temp = self.path.with_name(f"{self.path.stem}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            last_error: PermissionError | None = None
            for attempt in range(12):
                try:
                    os.replace(temp, self.path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            if last_error:
                raise last_error
        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except PermissionError:
                    pass

    def _seed(self) -> None:
        changed = False
        if not self.data["ppe"]:
            self.data["ppe"] = [
                PPE(code="helmet", name="Capacete", positive_class="Helmet", negative_class="No-Helmet").model_dump(mode="json"),
                PPE(code="gloves", name="Luvas", positive_class="Gloves", negative_class="No-Gloves").model_dump(mode="json"),
                PPE(code="goggles", name="\u00d3culos", positive_class="Goggles", negative_class="No-Goggles").model_dump(mode="json"),
            ]
            changed = True
        if not self.data["presets"]:
            preset = Preset(id="pre_default", name="Prote\u00e7\u00e3o completa", ppe_codes=["helmet", "gloves", "goggles"])
            self.data["presets"].append(preset.model_dump(mode="json"))
            self.data["job_roles"].append(JobRole(id="job_operator", name="Operador", preset_id=preset.id).model_dump(mode="json"))
            self.data["areas"].append(Area(id="area_factory", name="\u00c1rea industrial", preset_id=preset.id).model_dump(mode="json"))
            changed = True
        if not self.data["users"]:
            self.data["users"] = [
                User(
                    id="usr_admin",
                    name="Administrador",
                    username="admin",
                    password_hash=hash_password("admin123"),
                    role=UserRole.admin,
                ).model_dump(mode="json"),
                User(
                    id="usr_employee",
                    name="Funcion\u00e1rio Demo",
                    username="funcionario",
                    password_hash=hash_password("func123"),
                    role=UserRole.employee,
                    job_role_id="job_operator",
                    area_id="area_factory",
                ).model_dump(mode="json"),
            ]
            changed = True
        area_presets = {area["id"]: area.get("preset_id") for area in self.data["areas"]}
        job_presets = {job["id"]: job.get("preset_id") for job in self.data["job_roles"]}
        for user in self.data["users"]:
            if user.get("role") == UserRole.employee.value and not user.get("preset_id"):
                preset_id = area_presets.get(user.get("area_id")) or job_presets.get(user.get("job_role_id"))
                if preset_id:
                    user["preset_id"] = preset_id
                    changed = True
        if changed:
            self._write()

    def list(self, collection: str, model: type[T]) -> list[T]:
        with self._lock:
            return [model.model_validate(item) for item in self.data[collection]]

    def get(self, collection: str, item_id: str, model: type[T], id_field: str = "id") -> T | None:
        with self._lock:
            item = next((item for item in self.data[collection] if item.get(id_field) == item_id), None)
            return model.model_validate(item) if item else None

    def upsert(self, collection: str, value: BaseModel, id_field: str = "id") -> None:
        payload = value.model_dump(mode="json")
        identity = payload[id_field]
        with self._lock:
            for index, item in enumerate(self.data[collection]):
                if item.get(id_field) == identity:
                    self.data[collection][index] = payload
                    self._write()
                    return
            self.data[collection].append(payload)
            self._write()

    def delete(self, collection: str, item_id: str, id_field: str = "id") -> bool:
        with self._lock:
            original = len(self.data[collection])
            self.data[collection] = [item for item in self.data[collection] if item.get(id_field) != item_id]
            changed = len(self.data[collection]) != original
            if changed:
                self._write()
            return changed



