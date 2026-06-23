from pathlib import Path

from app.models import User
from app.store import JsonStore


def test_store_seeds_and_persists_atomically(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")

    users = store.list("users", User)
    assert any(user.username == "admin" for user in users)
    assert (tmp_path / "store.json").exists()
    assert not (tmp_path / "store.tmp").exists()


def test_store_upsert_replaces_item(tmp_path: Path):
    store = JsonStore(tmp_path / "store.json")
    admin = next(user for user in store.list("users", User) if user.username == "admin")
    admin.name = "Novo Admin"
    store.upsert("users", admin)

    loaded = store.get("users", admin.id, User)
    assert loaded is not None
    assert loaded.name == "Novo Admin"

