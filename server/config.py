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
APP_CONFIG_REFERENCE_PREFIX = "@Microsoft.AppConfiguration("
APP_CONFIG_ENVIRONMENT_VARIABLES = (
    "MAINTENANCE_MODE",
    "AI_ASSISTANT_ENABLED",
    "ROOM_EXPIRE_MINUTES",
    "LEADERBOARD_LIMIT",
)


def get_database_url():
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_secret_key():
    return os.getenv("SECRET_KEY")


def get_admin_job_key():
    key = os.getenv("ADMIN_JOB_KEY")
    if key:
        return key
    if os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"):
        return None
    return "test-job-key"


def is_unresolved_app_config_reference(value: str | None) -> bool:
    return bool(value and value.strip().startswith(APP_CONFIG_REFERENCE_PREFIX))


def parse_bool_env_value(value: str | None, default: bool) -> bool:
    if value is None or is_unresolved_app_config_reference(value):
        return default

    normalized_value = value.strip().casefold()
    if normalized_value in {"true", "1", "yes", "on"}:
        return True
    if normalized_value in {"false", "0", "no", "off"}:
        return False
    return default


def parse_int_env_value(
    value: str | None,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if value is None or is_unresolved_app_config_reference(value):
        return default

    try:
        parsed_value = int(value.strip(), 10)
    except (TypeError, ValueError):
        return default

    if minimum is not None and parsed_value < minimum:
        return default
    if maximum is not None and parsed_value > maximum:
        return default
    return parsed_value


def app_config_references_resolved() -> bool:
    return not any(
        is_unresolved_app_config_reference(os.getenv(name))
        for name in APP_CONFIG_ENVIRONMENT_VARIABLES
    )


def get_app_configuration_status():
    return {
        "source": "app_configuration_reference",
        "references_resolved": app_config_references_resolved(),
        "maintenance_mode": parse_bool_env_value(
            os.getenv("MAINTENANCE_MODE"),
            default=False,
        ),
        "ai_assistant_enabled": parse_bool_env_value(
            os.getenv("AI_ASSISTANT_ENABLED"),
            default=True,
        ),
        "room_expire_minutes": parse_int_env_value(
            os.getenv("ROOM_EXPIRE_MINUTES"),
            default=30,
            minimum=1,
        ),
        "leaderboard_limit": parse_int_env_value(
            os.getenv("LEADERBOARD_LIMIT"),
            default=10,
            minimum=1,
            maximum=100,
        ),
    }


def get_openai_endpoint_type(endpoint: str) -> str:
    normalized_endpoint = (endpoint or "").lower()
    if "services.ai.azure.com" in normalized_endpoint:
        return "foundry_project"
    return "azure_openai"


def get_foundry_openai_base_url(endpoint: str) -> str:
    normalized_endpoint = (endpoint or "").strip().rstrip("/")
    if not normalized_endpoint:
        return ""
    if normalized_endpoint.lower().endswith("/openai/v1"):
        return normalized_endpoint
    return f"{normalized_endpoint}/openai/v1"


def get_azure_openai_settings():
    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    endpoint_type = get_openai_endpoint_type(endpoint)
    return {
        "endpoint": endpoint,
        "api_key": (os.getenv("AZURE_OPENAI_API_KEY") or "").strip(),
        "deployment": (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip(),
        "api_version": (
            os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21"
        ).strip()
        or "2024-10-21",
        "openai_endpoint_type": endpoint_type,
        "foundry_base_url": (
            get_foundry_openai_base_url(endpoint)
            if endpoint_type == "foundry_project"
            else ""
        ),
    }


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
