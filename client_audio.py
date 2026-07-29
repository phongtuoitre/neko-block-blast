import logging


LOGGER = logging.getLogger(__name__)
_match_music_path = None
_match_music_playing = False


def play_match_music(music_path, *, volume=0.3, mixer=None):
    global _match_music_path, _match_music_playing

    mixer = _resolve_mixer(mixer)
    if mixer is None or not _mixer_is_ready(mixer):
        _reset_match_audio_state()
        return False

    music = getattr(mixer, "music", None)
    if music is None:
        _reset_match_audio_state()
        return False

    if _match_music_playing and _match_music_path == music_path:
        try:
            if music.get_busy():
                return False
        except Exception:
            pass

    try:
        music.load(music_path)
        if volume is not None:
            music.set_volume(volume)
        music.play(-1)
    except Exception:
        LOGGER.debug("Could not start match music", exc_info=True)
        _reset_match_audio_state()
        return False

    _match_music_path = music_path
    _match_music_playing = True
    return True


def stop_match_audio(*, fadeout_ms=200, mixer=None):
    mixer = _resolve_mixer(mixer)
    try:
        if mixer is not None and _mixer_is_ready(mixer):
            music = getattr(mixer, "music", None)
            if music is not None:
                try:
                    if fadeout_ms and hasattr(music, "fadeout"):
                        music.fadeout(fadeout_ms)
                    else:
                        music.stop()
                except Exception:
                    pass
            try:
                mixer.stop()
            except Exception:
                pass
    finally:
        _reset_match_audio_state()


def _resolve_mixer(mixer):
    if mixer is not None:
        return mixer
    try:
        import pygame
    except Exception:
        return None
    return getattr(pygame, "mixer", None)


def _mixer_is_ready(mixer):
    get_init = getattr(mixer, "get_init", None)
    if get_init is None:
        return True
    try:
        return bool(get_init())
    except Exception:
        return False


def _reset_match_audio_state():
    global _match_music_path, _match_music_playing
    _match_music_path = None
    _match_music_playing = False
