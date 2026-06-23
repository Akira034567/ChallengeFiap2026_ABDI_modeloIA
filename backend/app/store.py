from __future__ import annotations

import json
import threading
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
        self._seed()

    def _empty(self) -> dict[str, list[dict[str, Any]]]:
        return {name: [] for name in self.collections}

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return self._empty()
        with self.path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        for name in self.collections:
            loaded.setdefault(name, [])
        return loaded

    def _write(self) -> None:
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
        temp.replace(self.path)

    def _seed(self) -> None:
        changed = False
        if not self.data["ppe"]:
            self.data["ppe"] = [
                PPE(code="helmet", name="Capacete", positive_class="Helmet", negative_class="No-Helmet").model_dump(mode="json"),
                PPE(code="gloves", name="Luvas", positive_class="Gloves", negative_class="No-Gloves").model_dump(mode="json"),
                PPE(code="goggles", name="Óculos", positive_class="Goggles", negative_class="No-Goggles").model_dump(mode="json"),
            ]
            changed = True
        if not self.data["presets"]:
            preset = Preset(id="pre_default", name="Proteção completa", ppe_codes=["helmet", "gloves", "goggles"])
            self.data["presets"].append(preset.model_dump(mode="json"))
            self.data["job_roles"].append(JobRole(id="job_operator", name="Operador", preset_id=preset.id).model_dump(mode="json"))
            self.data["areas"].append(Area(id="area_factory", name="Área industrial", preset_id=preset.id).model_dump(mode="json"))
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
                    name="Funcionário Demo",
                    username="funcionario",
                    password_hash=hash_password("func123"),
                    role=UserRole.employee,
                    job_role_id="job_operator",
                    area_id="area_factory",
                ).model_dump(mode="json"),
            ]
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


