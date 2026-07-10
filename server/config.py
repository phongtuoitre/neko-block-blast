import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'neko_game.db'}"

load_dotenv(BASE_DIR / ".env")

SERVICE_NAME = "neko-block-blast-api"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ALGORITHM = "HS256"


def get_database_url():
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_secret_key():
    return os.getenv("SECRET_KEY")


def get_smtp_settings():
    required = {
        "host": os.getenv("SMTP_HOST"),
        "username": os.getenv("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD"),
        "email_from": os.getenv("EMAIL_FROM"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "SMTP configuration is incomplete: " + ", ".join(missing)
        )
    return {
        **required,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "from_name": os.getenv("EMAIL_FROM_NAME", "Neko Block Blast"),
    }
