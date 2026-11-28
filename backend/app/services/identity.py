"""Identity: register/login, pseudonyms, sealed vault, opt-in reveal, custodian break-glass. Owner: Rithwik.

Plan section 3.
* Registration stores the account (email + argon2 hash) and one vault row (pseudonym, sealed email).
  No column links the two zones: the pseudonym is recomputed from the email with the HMAC key.
* The identity map is our HashMap: pseudonym -> display tag, plus display tag -> pseudonyms
  (tags can collide), rebuilt from identity_vault on startup. The custodian looks people up in it.
* Break-glass: the reason is committed to audit_log first; only then is one vault row unsealed with
  the private key the custodian supplies. The key is never stored or logged.

Errors: EmailTaken (-> 409), BadCredentials (-> 401), PseudonymNotFound (-> 404),
AmbiguousTag (-> 409), auth.BadKey / ValueError (-> 400), auth.VaultNotConfigured (-> 503).
"""

import re
import threading

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, clock
from app.ds import HashMap
from app.models import Account, AuditLog, IdentityVault
from app.services import booking

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128
MIN_REASON = 10
ROLE_NAMES = {"S": "Student", "C": "Counsellor", "A": "Wellbeing team", "K": "Custodian"}


class EmailTaken(Exception):
    pass


class BadCredentials(Exception):
    pass


class PseudonymNotFound(KeyError):
    pass


class AmbiguousTag(Exception):
    pass


_lock = threading.RLock()
_tags = HashMap()     # pseudonym -> display tag
_by_tag = HashMap()   # display tag -> list of pseudonyms
_dummy_hash: str | None = None


# --- startup ----------------------------------------------------------------------------------

def _add_to_map(tags: HashMap, by_tag: HashMap, pseudonym: str) -> None:
    t = auth.display_tag(pseudonym)
    tags.put(pseudonym, t)
    if not by_tag.contains(t):
        by_tag.put(t, [])
    by_tag.get(t).append(pseudonym)


def rebuild(db: Session) -> None:
    """The identity map from identity_vault (pseudonyms only; the vault stays sealed)."""
    global _tags, _by_tag
    tags, by_tag = HashMap(), HashMap()
    for pse in db.scalars(select(IdentityVault.pseudonym)):
        _add_to_map(tags, by_tag, pse)
    with _lock:
        _tags, _by_tag = tags, by_tag


def student_count() -> int:
    with _lock:
        return len(_tags)


# --- accounts ------------------------------------------------------------------------------------

def _validate(email: str, password: str, name: str) -> str:
    email = auth.normalise_email(email)
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("enter a valid email address")
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise ValueError(f"passwords are {MIN_PASSWORD} to {MAX_PASSWORD} characters")
    if len(name.strip()) > 100:
        raise ValueError("name is at most 100 characters")
    return email


def _create(db: Session, email: str, password: str, role: str, name: str, vault: str | None) -> Account:
    if db.scalar(select(Account.id).where(Account.email == email)) is not None:
        raise EmailTaken(email)
    acc = Account(email=email, pw_hash=auth.hash_password(password), role=role, name=name.strip(),
                  created_at=clock.now())
    db.add(acc)
    if vault is not None:
        pse = auth.pseudonym_for(email)
        db.add(IdentityVault(pseudonym=pse, sealed_email=vault))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTaken(email) from exc
    if vault is not None:
        with _lock:
            _add_to_map(_tags, _by_tag, pse)
    return acc


def register(db: Session, email: str, password: str, name: str = "") -> Account:
    """A student account plus its sealed vault row (DB commit first, then the identity map)."""
    email = _validate(email, password, name)
    sealed = auth.seal(email)  # fails early, before any write, if the vault key is missing
    return _create(db, email, password, "S", name, sealed)


def create_staff(db: Session, email: str, password: str, role: str, name: str = "") -> Account:
    """Counsellor, admin or custodian account (seed.py; staff are not self-registered)."""
    if role not in ("C", "A", "K"):
        raise ValueError("staff role must be C, A or K")
    return _create(db, _validate(email, password, name), password, role, name, None)


def authenticate(db: Session, email: str, password: str) -> tuple[Account, str | None]:
    """(account, pseudonym or None) or BadCredentials. Unknown emails cost the same as wrong passwords."""
    global _dummy_hash
    acc = db.scalar(select(Account).where(Account.email == auth.normalise_email(email)))
    if acc is None:
        if _dummy_hash is None:
            _dummy_hash = auth.hash_password("not-a-real-password")
        auth.verify_password(password, _dummy_hash)
        raise BadCredentials()
    if not auth.verify_password(password, acc.pw_hash):
        raise BadCredentials()
    if auth.needs_rehash(acc.pw_hash):
        acc.pw_hash = auth.hash_password(password)
        db.commit()
    return acc, (auth.pseudonym_for(acc.email) if acc.role == "S" else None)


def token_for(acc: Account, pseudonym: str | None) -> str:
    return auth.create_token(acc.id, acc.role, pseudonym)


def me(db: Session, account_id: int, role: str, pseudonym: str | None) -> dict:
    """The caller's own profile. Students are shown by their tag; staff by name."""
    acc = db.get(Account, account_id)
    out = {"account_id": account_id, "role": role, "email": acc.email if acc else None,
           "pseudonym": None, "tag": None, "counsellor_id": None}
    if role == "S":
        out["pseudonym"], out["tag"] = pseudonym, auth.display_tag(pseudonym)
        out["display_name"] = f"Student {out['tag']}"
    else:
        name = (acc.name if acc else "") or ROLE_NAMES[role]
        if role == "C":
            try:
                rec = booking.counsellor_for_account(account_id)
                out["counsellor_id"], name = rec.id, rec.display_name
            except booking.CounsellorNotFound:
                pass
        out["display_name"] = name
    return out


# --- opt-in reveal ---------------------------------------------------------------------------------

def identity_blob(db: Session, account_id: int) -> str:
    """The student's name and email, encrypted with the server key, for a booking where they ticked
    "share my name with my counsellor". Only that booking row stores it."""
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    text = f"{acc.name} <{acc.email}>" if acc.name else acc.email
    return auth.encrypt_identity(text)


def reveal_text(blob: str | None) -> str | None:
    """Decrypt an opt-in identity for the booking's counsellor; None if absent or unreadable."""
    if not blob:
        return None
    try:
        return auth.decrypt_identity(blob)
    except auth.BadKey:
        return None


# --- custodian break-glass ------------------------------------------------------------------------------

def _audit(db: Session, actor_id: int, action: str, target: str, reason: str) -> AuditLog:
    row = AuditLog(actor_id=actor_id, action=action, target=target[:80], reason=reason, at=clock.now())
    db.add(row)
    db.commit()
    return row


def resolve(target: str) -> str:
    """A full pseudonym, or a display tag ("#47C32E" / "47c32e") that matches exactly one student."""
    target = target.strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", target):
        pse = target.lower()
        with _lock:
            if _tags.contains(pse):
                return pse
        raise PseudonymNotFound(target)
    t = "#" + target.lstrip("#").upper()
    with _lock:
        matches = list(_by_tag.get(t, []))
    if not matches:
        raise PseudonymNotFound(target)
    if len(matches) > 1:
        raise AmbiguousTag(f"{len(matches)} students share {t}; enter the full pseudonym")
    return matches[0]


def break_glass(db: Session, actor_id: int, target: str, reason: str, private_key: str) -> dict:
    """Write the reason to the audit log, then unseal one vault row. The outcome is logged as well."""
    reason = reason.strip()
    if len(reason) < MIN_REASON:
        raise ValueError(f"give a reason of at least {MIN_REASON} characters")
    if not target.strip():
        raise ValueError("enter a pseudonym or display tag")
    entry = _audit(db, actor_id, "break_glass", target.strip(), reason)  # 1. audit first, always
    try:
        pse = resolve(target)
        row = db.get(IdentityVault, pse)
        if row is None:
            raise PseudonymNotFound(target)
        email = auth.unseal(row.sealed_email, private_key)  # 2. then unseal, with the key they hold
    except Exception as exc:
        _audit(db, actor_id, "break_glass_failed", target.strip(), type(exc).__name__)
        raise
    _audit(db, actor_id, "break_glass_revealed", pse, f"audit #{entry.id}")
    return {"pseudonym": pse, "tag": auth.display_tag(pse), "email": email, "audit_id": entry.id}


def audit_log(db: Session, limit: int = 200) -> list[dict]:
    rows = db.execute(select(AuditLog, Account).join(Account, Account.id == AuditLog.actor_id, isouter=True)
                      .order_by(AuditLog.id.desc()).limit(limit)).all()
    return [{"id": a.id, "at": a.at, "actor_id": a.actor_id,
             "actor": (acc.name or acc.email) if acc is not None else f"account {a.actor_id}",
             "action": a.action, "target": a.target, "reason": a.reason} for a, acc in rows]
