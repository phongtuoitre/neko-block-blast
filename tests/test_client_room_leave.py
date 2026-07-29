import importlib
import sys
import types

from client_api import ApiError


class FakeFont:
    def set_bold(self, bold):
        self.bold = bold


def make_fake_pygame():
    fake = types.SimpleNamespace()
    fake.init = lambda: None
    fake.font = types.SimpleNamespace(
        match_font=lambda name: "fake-font",
        Font=lambda path, size: FakeFont(),
        SysFont=lambda name, size, bold=False: FakeFont(),
    )
    return fake


class FakeFuture:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, *args):
        self.warnings.append(args)


def import_launcher_with_fake_pygame(monkeypatch):
    sys.modules.pop("launcher", None)
    monkeypatch.setitem(sys.modules, "pygame", make_fake_pygame())
    launcher_module = importlib.import_module("launcher")
    launcher_module.LOGGER = FakeLogger()
    return launcher_module


def make_launcher_instance(launcher_module):
    launcher = launcher_module.Launcher.__new__(launcher_module.Launcher)
    launcher.current_room = {"room_code": "ABC123", "status": "waiting"}
    launcher.room_poll_future = FakeFuture()
    launcher.launching_match = True
    launcher.current_match_started = 123
    launcher.leave_room_in_progress = False
    launcher.online_error = "old error"
    launcher.online_message = "old message"
    launcher.state = launcher_module.STATE_ROOM_WAITING
    return launcher


def test_client_leave_room_success_clears_local_state_and_stops_polling(monkeypatch):
    launcher_module = import_launcher_with_fake_pygame(monkeypatch)
    launcher = make_launcher_instance(launcher_module)
    leave_calls = []
    stop_audio_calls = []
    monkeypatch.setattr(
        launcher_module,
        "leave_room",
        lambda token, room_code: leave_calls.append((token, room_code)),
    )
    monkeypatch.setattr(
        launcher_module,
        "stop_match_audio",
        lambda: stop_audio_calls.append("stop"),
    )
    launcher.access_token = "token"

    launcher_module.Launcher.leave_current_room(launcher)

    assert leave_calls == [("token", "ABC123")]
    assert launcher.current_room is None
    assert launcher.room_poll_future is None
    assert launcher.launching_match is False
    assert launcher.current_match_started is None
    assert launcher.leave_room_in_progress is False
    assert launcher.state == launcher_module.STATE_ONLINE_LOBBY
    assert stop_audio_calls


def test_client_leave_room_already_left_error_still_returns_to_lobby(monkeypatch):
    launcher_module = import_launcher_with_fake_pygame(monkeypatch)
    launcher = make_launcher_instance(launcher_module)
    monkeypatch.setattr(
        launcher_module,
        "leave_room",
        lambda token, room_code: (_ for _ in ()).throw(
            ApiError("http", "Player is not in room", 404)
        ),
    )
    monkeypatch.setattr(launcher_module, "stop_match_audio", lambda: None)
    launcher.access_token = "token"

    launcher_module.Launcher.leave_current_room(launcher)

    assert launcher.current_room is None
    assert launcher.room_poll_future is None
    assert launcher.leave_room_in_progress is False
    assert launcher.state == launcher_module.STATE_ONLINE_LOBBY
    assert launcher.online_error == ""


def test_client_leave_room_in_progress_does_not_send_second_request(monkeypatch):
    launcher_module = import_launcher_with_fake_pygame(monkeypatch)
    launcher = make_launcher_instance(launcher_module)
    launcher.leave_room_in_progress = True
    monkeypatch.setattr(
        launcher_module,
        "leave_room",
        lambda token, room_code: (_ for _ in ()).throw(AssertionError("called")),
    )

    launcher_module.Launcher.leave_current_room(launcher)

    assert launcher.current_room == {"room_code": "ABC123", "status": "waiting"}
    assert launcher.leave_room_in_progress is True
