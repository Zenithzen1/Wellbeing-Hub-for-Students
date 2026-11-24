import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App client backed by a throwaway SQLite file, so tests never touch hub.db."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", engine)
    db.SessionLocal.configure(bind=engine)

    from app.main import app

    with TestClient(app) as c:
        yield c
