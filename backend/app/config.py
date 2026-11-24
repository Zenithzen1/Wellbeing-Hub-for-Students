"""Settings, read from the environment or from the repo-root .env file (never committed).

Copy .env.example to .env and fill in real secrets.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_name: str = "Well-Being Hub"
    database_url: str = "sqlite:///./hub.db"

    # Secrets: the dev defaults below are placeholders and must be replaced in .env.
    hmac_key: str = "dev-only-hmac-key-change-me"        # email -> pseudonym (HMAC-SHA256)
    jwt_secret: str = "dev-only-jwt-secret-change-me"    # session cookie signing
    vault_public_key: str = ""                           # SealedBox public key (custodian keeps the private one)

    scheduler_interval_seconds: float = 15.0


settings = Settings()
