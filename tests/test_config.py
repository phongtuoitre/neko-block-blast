import os
import tempfile
from pathlib import Path

import pytest


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-config-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from server.config import (  # noqa: E402
    APP_CONFIG_ENVIRONMENT_VARIABLES,
    get_app_configuration_status,
    parse_bool_env_value,
    parse_int_env_value,
)
from server.main import app  # noqa: E402


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_app_config_env(monkeypatch):
    for name in APP_CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_app_configuration_status_uses_defaults():
    assert get_app_configuration_status() == {
        "source": "app_configuration_reference",
        "references_resolved": True,
        "maintenance_mode": False,
        "ai_assistant_enabled": True,
        "room_expire_minutes": 30,
        "leaderboard_limit": 10,
    }


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", " TRUE "])
def test_parse_boolean_true_values(value):
    assert parse_bool_env_value(value, default=False) is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", " FALSE "])
def test_parse_boolean_false_values(value):
    assert parse_bool_env_value(value, default=True) is False


def test_parse_integer_values():
    assert parse_int_env_value("45", default=30, minimum=1) == 45
    assert parse_int_env_value("100", default=10, minimum=1, maximum=100) == 100


@pytest.mark.parametrize("value", ["abc", "3.14", ""])
def test_parse_integer_bad_format_uses_default(value):
    assert parse_int_env_value(value, default=30, minimum=1) == 30


@pytest.mark.parametrize("value", ["0", "-5", "101"])
def test_parse_integer_out_of_range_uses_default(value):
    assert parse_int_env_value(value, default=10, minimum=1, maximum=100) == 10


def test_unresolved_app_configuration_reference_uses_defaults(monkeypatch):
    raw_reference = (
        "@Microsoft.AppConfiguration("
        "Endpoint=https://appcs-neko-block-nhom2.azconfig.io;Key=MAINTENANCE_MODE)"
    )
    monkeypatch.setenv("MAINTENANCE_MODE", raw_reference)
    monkeypatch.setenv("AI_ASSISTANT_ENABLED", "false")
    monkeypatch.setenv("ROOM_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("LEADERBOARD_LIMIT", "25")

    status = get_app_configuration_status()

    assert status["references_resolved"] is False
    assert status["maintenance_mode"] is False
    assert status["ai_assistant_enabled"] is False
    assert status["room_expire_minutes"] == 15
    assert status["leaderboard_limit"] == 25
    assert raw_reference not in repr(status)


def test_config_status_endpoint_returns_http_200():
    response = client.get("/config/status")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "app_configuration_reference"
    assert {
        "references_resolved",
        "maintenance_mode",
        "ai_assistant_enabled",
        "room_expire_minutes",
        "leaderboard_limit",
    }.issubset(data)
    forbidden_keys = {
        "DATABASE_URL",
        "SECRET_KEY",
        "PASSWORD",
        "API_KEY",
        "TOKEN",
        "CONNECTION_STRING",
    }
    assert forbidden_keys.isdisjoint(data)
