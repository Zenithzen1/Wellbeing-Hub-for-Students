"""seed.py: makes every page's demo data, logs in with the demo password, and runs only once."""

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select

import seed
from app import auth
from app.config import settings
from app.models import Account, IdentityVault, Resource
from app.services import analytics, booking, identity, recommend, waitlist


@pytest.fixture
def svc(db, monkeypatch):
    monkeypatch.setattr(settings, "vault_public_key", auth.generate_vault_keys()[0])
    monkeypatch.setattr(auth, "_hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))  # fast
    for svc_module in (identity, booking, waitlist, recommend):
        svc_module.rebuild(db)
    return db


def test_seed(svc):
    made = seed.seed(svc)
    assert made["staff"] == 5 and made["students"] == 40 and made["counsellors"] == 3
    assert svc.scalar(select(func.count()).select_from(Account)) == 45
    assert svc.scalar(select(func.count()).select_from(IdentityVault)) == 40
    assert svc.scalar(select(func.count()).select_from(Resource)) == 30
    assert seed.seed(svc) is None  # only once

    acc, pse = identity.authenticate(svc, "student01@students.example", seed.DEMO_PASSWORD)
    assert recommend.interests(svc, pse) == ["exams", "sleep"]
    assert len(recommend.recommend(svc, pse, 5)["items"]) == 5
    assert identity.authenticate(svc, "custodian@staff.example", seed.DEMO_PASSWORD)[0].role == "K"
    analytics.summary(svc)  # runs on the seeded data
