"""Identity: pseudonyms, accounts, tokens, opt-in reveal, vault and break-glass (plan section 3)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import auth, clock
from app.config import settings
from app.models import Account, AuditLog, IdentityVault
from app.services import identity


@pytest.fixture
def svc(db, monkeypatch):
    """Service session with a fresh vault key pair; .private is the custodian's key."""
    public, private = auth.generate_vault_keys()
    monkeypatch.setattr(settings, "vault_public_key", public)
    identity.rebuild(db)
    db.private = private
    return db


def test_pseudonym_is_keyed_normalised_and_stable(monkeypatch):
    a = auth.pseudonym_for("25a1cseb0101@iitdabudhabi.ac.ae")
    assert a == auth.pseudonym_for("  25A1CSEB0101@IITDABUDHABI.AC.AE ")
    assert len(a) == 64 and int(a, 16) >= 0
    assert a != auth.pseudonym_for("25a1cseb0102@iitdabudhabi.ac.ae")
    monkeypatch.setattr(settings, "hmac_key", "another-key")
    assert auth.pseudonym_for("25a1cseb0101@iitdabudhabi.ac.ae") != a  # without K, no candidate can be computed
    assert auth.display_tag(a) == "#" + a[:6].upper()


def test_register_and_login(svc):
    acc = identity.register(svc, " Student@Uni.ac.ae ", "correct horse", "Asha")
    assert acc.email == "student@uni.ac.ae" and acc.role == "S" and acc.pw_hash.startswith("$argon2")
    pse = auth.pseudonym_for("student@uni.ac.ae")
    vault = svc.get(IdentityVault, pse)
    assert vault is not None and "student@uni.ac.ae" not in vault.sealed_email
    assert identity.student_count() == 1

    with pytest.raises(identity.EmailTaken):
        identity.register(svc, "STUDENT@uni.ac.ae", "another password")
    got, got_pse = identity.authenticate(svc, "student@UNI.ac.ae", "correct horse")
    assert got.id == acc.id and got_pse == pse
    for email, pw in (("student@uni.ac.ae", "wrong password"), ("nobody@uni.ac.ae", "correct horse")):
        with pytest.raises(identity.BadCredentials):
            identity.authenticate(svc, email, pw)


@pytest.mark.parametrize("email,pw", [("not-an-email", "longenough"), ("a@b.c", "short"), ("a b@c.de", "longenough")])
def test_register_validates(svc, email, pw):
    with pytest.raises(ValueError):
        identity.register(svc, email, pw)


def test_register_needs_the_vault_key(svc, monkeypatch):
    monkeypatch.setattr(settings, "vault_public_key", "")
    with pytest.raises(auth.VaultNotConfigured):
        identity.register(svc, "x@uni.ac.ae", "longenough")
    assert svc.scalar(select(func.count()).select_from(Account)) == 0  # nothing half-written


def test_staff_have_no_vault_row(svc):
    acc = identity.create_staff(svc, "noor@uni.ac.ae", "longenough", "C", "Dr Noor")
    _, pse = identity.authenticate(svc, "noor@uni.ac.ae", "longenough")
    assert acc.role == "C" and pse is None
    assert svc.scalar(select(func.count()).select_from(IdentityVault)) == 0
    with pytest.raises(ValueError):
        identity.create_staff(svc, "s@uni.ac.ae", "longenough", "S")


def test_token_roundtrip_expiry_and_tampering(db):  # db: clock frozen at T0
    token = auth.create_token(7, "S", "a" * 64)
    claims = auth.decode_token(token)
    assert claims["sub"] == "7" and claims["role"] == "S" and claims["pse"] == "a" * 64
    with pytest.raises(auth.InvalidToken):
        auth.decode_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    with pytest.raises(auth.InvalidToken):
        auth.decode_token(auth.create_token(7, "S"))  # a student token must carry the pseudonym
    clock.advance(timedelta(hours=settings.session_hours, seconds=1))
    with pytest.raises(auth.InvalidToken):
        auth.decode_token(token)


def test_opt_in_identity_roundtrip(svc):
    acc = identity.register(svc, "asha@uni.ac.ae", "longenough", "Asha K")
    blob = identity.identity_blob(svc, acc.id)
    assert "asha" not in blob
    assert identity.reveal_text(blob) == "Asha K <asha@uni.ac.ae>"
    assert identity.reveal_text(None) is None and identity.reveal_text("garbage") is None


def test_break_glass_audits_first_and_needs_the_private_key(svc):
    identity.register(svc, "asha@uni.ac.ae", "longenough")
    custodian = identity.create_staff(svc, "k@uni.ac.ae", "longenough", "K", "Custodian")
    pse = auth.pseudonym_for("asha@uni.ac.ae")
    reason = "Safety concern raised by Dr Noor"

    with pytest.raises(ValueError):
        identity.break_glass(svc, custodian.id, pse, "too short", svc.private)
    _, wrong = auth.generate_vault_keys()
    with pytest.raises(auth.BadKey):
        identity.break_glass(svc, custodian.id, pse, reason, wrong)
    actions = list(svc.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == ["break_glass", "break_glass_failed"]  # the attempt is logged even though it failed

    out = identity.break_glass(svc, custodian.id, auth.display_tag(pse).lower(), reason, svc.private)
    assert out["email"] == "asha@uni.ac.ae" and out["pseudonym"] == pse
    log = identity.audit_log(svc)
    assert [e["action"] for e in log[:2]] == ["break_glass_revealed", "break_glass"]
    assert log[1]["reason"] == reason and log[1]["actor"] == "Custodian"

    with pytest.raises(identity.PseudonymNotFound):
        identity.break_glass(svc, custodian.id, "#000000", reason, svc.private)


def test_ambiguous_tag_needs_the_full_pseudonym(svc):
    identity.register(svc, "a@uni.ac.ae", "longenough")
    pse = auth.pseudonym_for("a@uni.ac.ae")
    twin = pse[:6] + ("0" if pse[6] != "0" else "1") + pse[7:]  # another student, same 6-hex tag
    identity._add_to_map(identity._tags, identity._by_tag, twin)
    with pytest.raises(identity.AmbiguousTag):
        identity.resolve(auth.display_tag(pse))
    assert identity.resolve(pse) == pse and identity.resolve(pse.upper()) == pse


def test_identity_map_rebuilds_from_the_vault(svc):
    identity.register(svc, "a@uni.ac.ae", "longenough")
    identity.register(svc, "b@uni.ac.ae", "longenough")
    identity.rebuild(svc)
    assert identity.student_count() == 2
    pse = auth.pseudonym_for("b@uni.ac.ae")
    assert identity.resolve(auth.display_tag(pse)) == pse
