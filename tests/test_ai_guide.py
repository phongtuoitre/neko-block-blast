import os
import tempfile
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-ai-guide-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import app  # noqa: E402


client = TestClient(app)

AZURE_ENV_NAMES = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def set_fake_azure_config(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-secret-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "unit-test-deployment")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")


def sample_game_state():
    return {
        "score": 120,
        "board": [[0 for _ in range(8)] for _ in range(8)],
        "current_blocks": [
            [[1, 1]],
            [[1], [1]],
            [[1]],
        ],
        "combo": 0,
    }


def post_chat(question, game_state=None):
    payload = {"question": question}
    if game_state is not None:
        payload["game_state"] = game_state
    return client.post("/api/ai-guide/chat", json=payload)


def test_chat_uses_configured_azure_openai(monkeypatch):
    set_fake_azure_config(monkeypatch)
    captured = {}

    def fake_completion(settings, messages, **kwargs):
        captured["settings"] = settings
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return FakeCompletion("Meo meo, hãy giữ khoảng trống ở giữa bàn nhé.")

    monkeypatch.setattr(
        "server.routers.ai_guide.create_openai_chat_completion",
        fake_completion,
    )

    response = post_chat("Mẹo cho người mới")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "azure_openai"
    assert data["used_fallback"] is False
    assert "Meo meo" in data["reply"]
    assert captured["settings"]["deployment"] == "unit-test-deployment"
    assert captured["kwargs"]["timeout_seconds"] == 12


def test_chat_rejects_empty_question():
    response = post_chat("   ")

    assert response.status_code == 422


def test_chat_rejects_too_long_question():
    response = post_chat("a" * 501)

    assert response.status_code == 422


def test_chat_falls_back_without_azure_openai_config(monkeypatch):
    for name in AZURE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    response = post_chat("Hướng dẫn cách chơi")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "fallback"
    assert data["used_fallback"] is True
    assert data["reply"]
    assert data["error"]


def test_chat_fallback_can_analyze_board_without_azure_config(monkeypatch):
    for name in AZURE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    response = post_chat(
        "Phân tích bàn chơi hiện tại",
        game_state=sample_game_state(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "fallback"
    assert "khối" in data["reply"].casefold()
    assert "gợi ý" in data["reply"].casefold()


def test_chat_falls_back_when_azure_openai_times_out(monkeypatch):
    set_fake_azure_config(monkeypatch)

    def fake_timeout(*args, **kwargs):
        raise TimeoutError("request timed out with fake-secret-key")

    monkeypatch.setattr(
        "server.routers.ai_guide.create_openai_chat_completion",
        fake_timeout,
    )

    response = post_chat("Làm sao để được nhiều điểm?")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "fallback"
    assert data["used_fallback"] is True
    assert "fake-secret-key" not in data["error"]
    assert data["reply"]


def test_chat_falls_back_when_azure_openai_returns_error(monkeypatch):
    set_fake_azure_config(monkeypatch)

    def fake_error(*args, **kwargs):
        raise RuntimeError("service failed for fake-secret-key")

    monkeypatch.setattr(
        "server.routers.ai_guide.create_openai_chat_completion",
        fake_error,
    )

    response = post_chat("Tôi nên đặt khối ở đâu?", game_state=sample_game_state())

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "fallback"
    assert data["used_fallback"] is True
    assert "fake-secret-key" not in data["error"]
    assert data["reply"]
