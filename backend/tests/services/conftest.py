from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import clock, models  # noqa: F401  (registers the tables)
from app.db import Base
from app.services import events, notify

T0 = datetime(2026, 11, 30, 6, 0, tzinfo=timezone.utc)  # Mon 30 Nov, 10:00 in Dubai


@pytest.fixture
def db(tmp_path):
    """A session on a throwaway SQLite file, fresh in-memory structures and a clock frozen at T0."""
    engine = create_engine(f"sqlite:///{tmp_path / 'svc.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    clock.freeze(T0)
    notify.reset()
    events.rebuild(session)
    notify.rebuild(session)
    yield session
    session.close()
    clock.unfreeze()
    engine.dispose()


@pytest.fixture
def channel(monkeypatch):
    """Replaces the email stub with a recorder; set .fail_for to a set of titles to make them fail."""

    class Recorder:
        def __init__(self):
            self.sent = []
            self.fail_for = set()

        def __call__(self, row):
            title = notify.to_dict(row)["title"]
            if title in self.fail_for:
                raise ConnectionError("smtp down")
            self.sent.append(title)

    rec = Recorder()
    monkeypatch.setattr(notify, "CHANNELS", [rec])
    return rec
