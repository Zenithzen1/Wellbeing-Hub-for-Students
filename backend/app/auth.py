"""Passwords (argon2), pseudonyms (HMAC-SHA256) and the JWT session cookie. Owner: Rithwik."""


def hash_password(password: str) -> str:
    raise NotImplementedError


def verify_password(password: str, pw_hash: str) -> bool:
    raise NotImplementedError


def pseudonym_for(email: str) -> str:
    """HMAC-SHA256(settings.hmac_key, normalised email) -> stable pseudonym."""
    raise NotImplementedError


def create_token(account_id: int, role: str) -> str:
    raise NotImplementedError


def decode_token(token: str) -> dict:
    raise NotImplementedError
