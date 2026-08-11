import importlib
import sys
import types

import pytest

import client_api
from client_api import ApiError


def test_fetch_public_leaderboard_maps_dashboard_rows(monkeypatch):
    calls = []

    def fake_request(path):
        calls.append(path)
        return {
            "leaderboard": [
                {
                    "rank": 1,
                    "username": "neko_user",
                    "display_name": "Neko Player",
                    "matches": 4,
                    "wins": 2,
                    "total_score": 4640,
                    "best_score": 2270,
                }
            ]
        }

    monkeypatch.setattr(client_api, "_request", fake_request)

    assert client_api.fetch_public_leaderboard() == [
        {
            "rank": 1,
            "name": "Neko Player",
            "matches": 4,
            "wins": 2,
            "total_score": 4640,
            "best_score": 2270,
        }
    ]
    assert calls == ["/public/dashboard"]


def test_fetch_public_leaderboard_handles_empty_list(monkeypatch):
    monkeypatch.setattr(client_api, "_request", lambda path: {"leaderboard": []})

    assert client_api.fetch_public_leaderboard() == []


def test_fetch_public_leaderboard_propagates_connection_error(monkeypatch):
    def raise_connection_error(path):
        raise ApiError("connection", "URLError")

    monkeypatch.setattr(client_api, "_request", raise_connection_error)

    with pytest.raises(ApiError) as exc_info:
        client_api.fetch_public_leaderboard()

    assert exc_info.value.kind == "connection"


def test_fetch_public_leaderboard_handles_missing_fields(monkeypatch):
    monkeypatch.setattr(
        client_api,
        "_request",
        lambda path: {
            "leaderboard": [
                {"username": "fallback_user"},
                {"display_name": "", "total_score": "bad"},
                "not a row",
            ]
        },
    )

    assert client_api.fetch_public_leaderboard() == [
        {
            "rank": 1,
            "name": "fallback_user",
            "matches": 0,
            "wins": 0,
            "total_score": 0,
            "best_score": 0,
        }
    ]


class FakeFont:
    def set_bold(self, bold):
        self.bold = bold


class DoneFuture:
    def done(self):
        return True

    def result(self):
        raise ApiError("connection", "URLError")


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, *args):
        self.warnings.append(args)


def make_fake_pygame():
    fake = types.SimpleNamespace()
    fake.init = lambda: None
    fake.font = types.SimpleNamespace(
        match_font=lambda name: "fake-font",
        Font=lambda path, size: FakeFont(),
        SysFont=lambda name, size, bold=False: FakeFont(),
    )
    return fake


def test_launcher_leaderboard_api_error_keeps_safe_empty_fallback(monkeypatch):
    sys.modules.pop("launcher", None)
    monkeypatch.setitem(sys.modules, "pygame", make_fake_pygame())
    launcher_module = importlib.import_module("launcher")
    launcher_module.LOGGER = FakeLogger()
    launcher = launcher_module.Launcher.__new__(launcher_module.Launcher)
    launcher.leaderboard_future = DoneFuture()
    launcher.leaderboard_loading = True
    launcher.leaderboard_entries = []
    launcher.leaderboard_error = ""

    launcher_module.Launcher.update_leaderboard_fetch(launcher)

    assert launcher.leaderboard_future is None
    assert launcher.leaderboard_loading is False
    assert launcher.leaderboard_entries == []
    assert launcher.leaderboard_error == "Không tải được bảng xếp hạng"
    assert launcher_module.LOGGER.warnings
