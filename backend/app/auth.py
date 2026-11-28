"""Passwords (argon2), pseudonyms (HMAC-SHA256), the JWT session cookie, and the two boxes. Owner: Rithwik.

Plan section 3. We write the data structures ourselves, never the cryptography: everything here
comes from vetted libraries (argon2-cffi, hmac/hashlib, PyJWT, PyNaCl).

* pseudonym = HMAC-SHA256(K, normalised email), 64 hex. K lives only in .env, so the
  "hash every possible roll number" attack (section 3.2) cannot compute a single candidate.
* Opt-in reveal: the student's name/email is encrypted with a server key (SecretBox) and stored on
  that one booking; the server can open it for that booking's counsellor.
* Vault: the email is sealed with the custodian's public key (SealedBox). The server can seal but
  never open; unsealing needs the private key, which only the custodian holds.
"""

import base64
import hashlib
import hmac
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.secret import SecretBox

from app import clock
from app.config import settings

COOKIE = "hub_session"
ALGORITHM = "HS256"
ROLES = ("S", "C", "A", "K")

_hasher = PasswordHasher()


class InvalidToken(Exception):
    """The session token is missing, forged, malformed or expired (-> 401)."""


class VaultNotConfigured(RuntimeError):
    """VAULT_PUBLIC_KEY is not set (run scripts/gen_keys.py)."""


class BadKey(ValueError):
    """The private key or ciphertext is wrong (-> 400)."""


# --- passwords --------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, pw_hash: str) -> bool:
    try:
        return _hasher.verify(pw_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(pw_hash: str) -> bool:
    return _hasher.check_needs_rehash(pw_hash)


# --- pseudonyms ---------------------------------------------------------------------------------

def normalise_email(email: str) -> str:
    """Trim and lower-case, or 25A1CSEB0101@... would become a second "person"."""
    return email.strip().lower()


def pseudonym_for(email: str) -> str:
    """HMAC-SHA256(settings.hmac_key, normalised email) -> stable pseudonym (64 hex)."""
    return hmac.new(settings.hmac_key.encode(), normalise_email(email).encode(), hashlib.sha256).hexdigest()


def display_tag(pseudonym: str) -> str:
    """For humans only, e.g. "#47C32E". Tags can collide; lookups always use the full pseudonym."""
    return "#" + pseudonym[:6].upper()


# --- session token --------------------------------------------------------------------------------

def create_token(account_id: int, role: str, pseudonym: str | None = None) -> str:
    """JWT {sub, role, pse (students only), iat, exp}. Times come from clock.now()."""
    now = clock.now()
    claims = {"sub": str(account_id), "role": role, "iat": int(now.timestamp()),
              "exp": int((now + timedelta(hours=settings.session_hours)).timestamp())}
    if pseudonym:
        claims["pse"] = pseudonym
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Verified claims. InvalidToken if the signature, shape or expiry is wrong.

    Expiry is checked against clock.now() (not the system clock), so frozen-clock tests behave.
    """
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM],
                            options={"verify_exp": False, "verify_iat": False, "require": ["sub", "role", "exp"]})
    except jwt.InvalidTokenError as exc:
        raise InvalidToken(str(exc)) from exc
    if claims["exp"] <= clock.now().timestamp():
        raise InvalidToken("session expired")
    if claims["role"] not in ROLES or not str(claims["sub"]).isdigit():
        raise InvalidToken("bad claims")
    if claims["role"] == "S" and not claims.get("pse"):
        raise InvalidToken("student token without a pseudonym")
    return claims


# --- opt-in reveal: server-key encryption ---------------------------------------------------------------

def _identity_box() -> SecretBox:
    # A separate 32-byte key derived from the server secret, so the HMAC key itself is never an encryption key.
    key = hmac.new(settings.hmac_key.encode(), b"wellbeing-hub opt-in identity v1", hashlib.sha256).digest()
    return SecretBox(key)


def encrypt_identity(text: str) -> str:
    return base64.b64encode(_identity_box().encrypt(text.encode())).decode()


def decrypt_identity(blob: str) -> str:
    try:
        return _identity_box().decrypt(base64.b64decode(blob)).decode()
    except (CryptoError, ValueError) as exc:
        raise BadKey("cannot decrypt identity") from exc


# --- the vault: seal with the public key, open only with the custodian's private key ---------------------

def generate_vault_keys() -> tuple[str, str]:
    """(public hex, private hex). The private half is printed once and never stored on the server."""
    sk = PrivateKey.generate()
    return bytes(sk.public_key).hex(), bytes(sk).hex()


def seal(email: str) -> str:
    if not settings.vault_public_key:
        raise VaultNotConfigured("VAULT_PUBLIC_KEY is not set; run scripts/gen_keys.py")
    try:
        box = SealedBox(PublicKey(bytes.fromhex(settings.vault_public_key)))
    except (ValueError, CryptoError) as exc:
        raise VaultNotConfigured("VAULT_PUBLIC_KEY is not a valid hex public key") from exc
    return base64.b64encode(box.encrypt(email.encode())).decode()


def unseal(sealed: str, private_key_hex: str) -> str:
    try:
        box = SealedBox(PrivateKey(bytes.fromhex(private_key_hex.strip())))
        return box.decrypt(base64.b64decode(sealed)).decode()
    except (ValueError, CryptoError) as exc:
        raise BadKey("this private key cannot open the vault") from exc
