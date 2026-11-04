"""System media playback controls using Windows multimedia keyboard events.

Controls whatever media player is currently active (Spotify, YouTube in Chrome/Edge,
VLC, Apple Music, Windows Media Player, etc.).
"""
import ctypes
from tools.registry import tool
from core.bus import BUS

# Windows Virtual Key Codes
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP       = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE      = 0xAD
VK_VOLUME_DOWN      = 0xAE
VK_VOLUME_UP        = 0xAF
KEYEVENTF_KEYUP     = 0x0002


def _send_vk(vk: int):
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        BUS.emit("tool", f"media key error: {e}")
        return False


@tool("media.play_pause", "Toggle play/pause for currently playing media (Spotify, YouTube, browser, media player).", {})
def media_play_pause(ctx=None):
    _send_vk(VK_MEDIA_PLAY_PAUSE)
    BUS.emit("tool", "media: play/pause toggled")
    return "play/pause toggled"


@tool("media.next", "Skip to the next song or video.", {})
def media_next(ctx=None):
    _send_vk(VK_MEDIA_NEXT_TRACK)
    BUS.emit("tool", "media: next track")
    return "skipped to next track"


@tool("media.previous", "Go back to the previous song or video.", {})
def media_previous(ctx=None):
    _send_vk(VK_MEDIA_PREV_TRACK)
    BUS.emit("tool", "media: previous track")
    return "returned to previous track"


@tool("media.stop", "Stop playback of currently playing media.", {})
def media_stop(ctx=None):
    _send_vk(VK_MEDIA_STOP)
    BUS.emit("tool", "media: stopped")
    return "media stopped"


@tool("media.volume_up", "Step master volume up.", {})
def media_volume_up(ctx=None):
    for _ in range(3):
        _send_vk(VK_VOLUME_UP)
    return "volume increased"


@tool("media.volume_down", "Step master volume down.", {})
def media_volume_down(ctx=None):
    for _ in range(3):
        _send_vk(VK_VOLUME_DOWN)
    return "volume decreased"


@tool("media.mute", "Toggle audio mute.", {})
def media_mute(ctx=None):
    _send_vk(VK_VOLUME_MUTE)
    return "mute toggled"

