"""Windows Accessibility tools: Magnifier, Narrator, High Contrast, Color Filters, On-Screen Keyboard."""
import ctypes, os, subprocess
from tools.registry import tool
from core.bus import BUS

VK_LWIN      = 0x5B
VK_CONTROL   = 0x11
VK_MENU      = 0x12  # Alt
VK_SHIFT     = 0x10
VK_RETURN    = 0x0D
VK_ESCAPE    = 0x1B
VK_OEM_PLUS  = 0xBB
VK_OEM_MINUS = 0xBD
VK_C         = 0x43
KEYEVENTF_KEYUP = 0x0002


def _send_combo(*vks):
    try:
        user32 = ctypes.windll.user32
        for vk in vks:
            user32.keybd_event(vk, 0, 0, 0)
        for vk in reversed(vks):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        BUS.emit("tool", f"accessibility key combo error: {e}")
        return False


@tool("accessibility.magnifier", "Control the Windows screen magnifier: open, close, zoom_in, zoom_out.",
      {"action": {"type": "string", "description": "open | close | zoom_in | zoom_out"}})
def accessibility_magnifier(action="open", ctx=None):
    action = action.lower().strip()
    if action == "open":
        subprocess.Popen(["magnify.exe"])
        return "magnifier opened"
    elif action == "close":
        subprocess.run("taskkill /IM Magnify.exe /F", shell=True, capture_output=True)
        return "magnifier closed"
    elif action == "zoom_in":
        _send_combo(VK_LWIN, VK_OEM_PLUS)
        return "magnifier zoomed in"
    elif action == "zoom_out":
        _send_combo(VK_LWIN, VK_OEM_MINUS)
        return "magnifier zoomed out"
    return f"unknown magnifier action: {action}"


@tool("accessibility.narrator", "Control the Windows Narrator screen reader: start, stop, or toggle.",
      {"action": {"type": "string", "description": "start | stop | toggle"}})
def accessibility_narrator(action="toggle", ctx=None):
    action = action.lower().strip()
    if action == "stop":
        subprocess.run("taskkill /IM Narrator.exe /F", shell=True, capture_output=True)
        return "narrator stopped"
    elif action == "start":
        subprocess.Popen(["narrator.exe"])
        return "narrator started"
    else:  # toggle
        _send_combo(VK_LWIN, VK_CONTROL, VK_RETURN)
        return "narrator toggled"


@tool("accessibility.on_screen_keyboard", "Open or close the Windows On-Screen Keyboard (OSK).",
      {"action": {"type": "string", "description": "open | close"}})
def accessibility_osk(action="open", ctx=None):
    action = action.lower().strip()
    if action == "close":
        subprocess.run("taskkill /IM osk.exe /F", shell=True, capture_output=True)
        return "on-screen keyboard closed"
    subprocess.Popen(["osk.exe"])
    return "on-screen keyboard opened"


@tool("accessibility.high_contrast", "Toggle Windows High Contrast mode.", {})
def accessibility_high_contrast(ctx=None):
    os.system("start ms-settings:easeofaccess-highcontrast")
    return "opened high contrast settings"


@tool("accessibility.color_filter", "Toggle Windows color filters (grayscale, inverted, color blind mode).", {})
def accessibility_color_filter(ctx=None):
    _send_combo(VK_LWIN, VK_CONTROL, VK_C)
    return "color filter toggled"


@tool("accessibility.open_settings", "Open Windows accessibility / ease-of-access settings for a category.",
      {"category": {"type": "string", "description": "display | mouse | keyboard | audio | speech | captions | highcontrast"}})
def accessibility_open_settings(category="display", ctx=None):
    cat = category.lower().strip()
    uris = {
        "display": "ms-settings:easeofaccess-display",
        "mouse": "ms-settings:easeofaccess-mouse",
        "keyboard": "ms-settings:easeofaccess-keyboard",
        "audio": "ms-settings:easeofaccess-audio",
        "speech": "ms-settings:easeofaccess-speechrecognition",
        "captions": "ms-settings:easeofaccess-closedcaptioning",
        "highcontrast": "ms-settings:easeofaccess-highcontrast",
        "magnifier": "ms-settings:easeofaccess-magnifier",
        "narrator": "ms-settings:easeofaccess-narrator",
        "colorfilter": "ms-settings:easeofaccess-colorfilter",
    }
    uri = uris.get(cat, "ms-settings:easeofaccess-display")
    os.system(f"start {uri}")
    return f"opened accessibility settings for {cat}"

