import importlib
import sys
import types

import pytest

import client_audio


class FakeMusic:
    def __init__(self):
        self.busy = False
        self.load_calls = []
        self.play_calls = 0
        self.stop_calls = 0
        self.fadeout_calls = []

    def load(self, path):
        self.load_calls.append(path)

    def set_volume(self, volume):
        self.volume = volume

    def play(self, loops):
        self.play_calls += 1
        self.loops = loops
        self.busy = True

    def stop(self):
        self.stop_calls += 1
        self.busy = False

    def fadeout(self, milliseconds):
        self.fadeout_calls.append(milliseconds)
        self.busy = False

    def get_busy(self):
        return self.busy


class FakeMixer:
    def __init__(self, initialized=True):
        self.initialized = initialized
        self.music = FakeMusic()
        self.stop_calls = 0

    def init(self):
        self.initialized = True

    def get_init(self):
        return self.initialized

    def stop(self):
        self.stop_calls += 1


class FakeFont:
    def set_bold(self, bold):
        self.bold = bold


def make_fake_pygame():
    fake = types.SimpleNamespace()
    fake.error = Exception
    fake.QUIT = 256
    fake.KEYDOWN = 768
    fake.K_ESCAPE = 27
    fake.K_RETURN = 13
    fake.mixer = FakeMixer()
    fake.init = lambda: None
    fake.font = types.SimpleNamespace(
        match_font=lambda name: "fake-font",
        Font=lambda path, size: FakeFont(),
        SysFont=lambda name, size, bold=False: FakeFont(),
    )
    fake.display = types.SimpleNamespace(
        flip=lambda: None,
        set_caption=lambda caption: None,
    )
    fake.event = types.SimpleNamespace(get=lambda: [])
    return fake


def import_block_blast_with_fake_pygame(monkeypatch):
    sys.modules.pop("block_blast_cat", None)
    monkeypatch.setitem(sys.modules, "pygame", make_fake_pygame())
    return importlib.import_module("block_blast_cat")


def test_stop_match_audio_can_be_called_repeatedly():
    mixer = FakeMixer()

    client_audio.stop_match_audio(mixer=mixer)
    client_audio.stop_match_audio(mixer=mixer)

    assert mixer.stop_calls == 2


def test_stop_match_audio_stops_music_and_sound_channels():
    mixer = FakeMixer()
    mixer.music.busy = True

    client_audio.stop_match_audio(mixer=mixer)

    assert mixer.music.fadeout_calls == [200]
    assert mixer.stop_calls == 1
    assert mixer.music.busy is False


def test_reentering_match_does_not_stack_music_tracks():
    mixer = FakeMixer()

    assert client_audio.play_match_music("bgm.mp3", mixer=mixer) is True
    assert client_audio.play_match_music("bgm.mp3", mixer=mixer) is False
    assert mixer.music.play_calls == 1

    client_audio.stop_match_audio(mixer=mixer, fadeout_ms=0)
    assert client_audio.play_match_music("bgm.mp3", mixer=mixer) is True
    assert mixer.music.play_calls == 2


def test_request_exit_stops_match_audio(monkeypatch):
    game_module = import_block_blast_with_fake_pygame(monkeypatch)
    game = game_module.Game.__new__(game_module.Game)
    game.online_poll_executor = None
    game.embedded = True
    game.running = True
    calls = []
    game.stop_match_audio = lambda: calls.append("stop")

    game_module.Game.request_exit(game)

    assert calls
    assert game.running is False


def test_game_over_stops_match_audio(monkeypatch):
    game_module = import_block_blast_with_fake_pygame(monkeypatch)
    game = game_module.Game.__new__(game_module.Game)
    game.available_blocks = [object()]
    game.can_place = lambda block, row, col: False
    game.online_mode = False
    game.save_leaderboard = lambda: None
    game.snd_gameover = types.SimpleNamespace(play=lambda: None)
    game.cat_surprise = types.SimpleNamespace(trigger=lambda: None)
    calls = []
    game.stop_match_audio = lambda: calls.append("stop")

    game_module.Game.check_game_over(game)

    assert calls
    assert game.game_over is True


def test_gameplay_loop_exception_still_stops_match_audio(monkeypatch):
    game_module = import_block_blast_with_fake_pygame(monkeypatch)
    game = game_module.Game.__new__(game_module.Game)
    game.running = True
    game.poll_online_match = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    calls = []
    game.stop_match_audio = lambda: calls.append("stop")

    with pytest.raises(RuntimeError):
        game_module.Game.run(game)

    assert calls
