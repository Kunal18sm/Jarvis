#computer_control.py
import io
import json
import platform
import re
import string
import subprocess
import sys

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}
import time
import random
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

try:
    import PIL.Image
    import PIL.ImageGrab
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "api_keys.json"
_MEMORY_PATH  = _BASE / "memory" / "long_term.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _platform_os() -> str:
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def _get_os() -> str:
    return _load_config().get("os_system", _platform_os()).lower()


def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")

_SAFE_SCREENSHOT_ROOTS = (
    Path.home(),
)

def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "jarvis_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)

    if dt == "last_name":
        return random.choice(_LAST_NAMES)

    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"

    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"

    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw   = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.digits)
            + random.choice("!@#$%")
            + "".join(random.choices(chars, k=9))
        )
        return "".join(random.sample(raw, len(raw)))

    if dt == "phone":
        return f"+1{random.randint(200,999)}{random.randint(1_000_000, 9_999_999)}"

    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"

    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"

    if dt == "zip_code":
        return str(random.randint(10000, 99999))

    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"

def _user_profile() -> dict:
    """Read identity fields from long-term memory."""
    try:
        if _MEMORY_PATH.exists():
            data     = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            return {k: v.get("value", "") for k, v in identity.items()}
    except Exception:
        pass
    return {}

def _paste_or_type(text: str) -> None:
    _require_pyautogui()
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.08)
        paste_key = "command" if _get_os() == "mac" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
        time.sleep(0.08)
    else:
        pyautogui.typewrite(text, interval=0.03)

def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.2)
    _paste_or_type(text)
    return f"Typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)
    _paste_or_type(text)
    return f"Smart-typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Double-c' if clicks == 2 else 'C'}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical   = direction in ("up", "down")
    clicks     = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"Scrolled {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x1, y1, duration=0.2)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")
    return f"Dragged ({x1},{y1}) → ({x2},{y2})"


def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(copied — pyperclip unavailable for read)"


def _clipboard_paste(text: str) -> str:
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        paste_key = "command" if _get_os() == "mac" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
        return f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip not available"


def _capture_screen_image():
    """
    Capture the current desktop screen safely across platforms and Windows DPI contexts.
    Tries PyQt6 QScreen, mss, PIL.ImageGrab, and PyAutoGUI in order.
    """
    # 1. PyQt6 QScreen (best fidelity inside GUI app)
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QBuffer, QIODevice
        import PIL.Image
        app = QApplication.instance()
        if not app:
            import sys
            app = QApplication(sys.argv if hasattr(sys, 'argv') and sys.argv else ["jarvis"])
        if app:
            screen = app.primaryScreen()
            if screen:
                pix = screen.grabWindow(0)
                if not pix.isNull() and pix.width() > 100:
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.ReadWrite)
                    pix.save(buf, "PNG")
                    raw = bytes(buf.data())
                    if len(raw) > 1000:
                        im = PIL.Image.open(io.BytesIO(raw)).convert("RGB")
                        return im
    except Exception:
        pass

    # 2. mss (direct display capture)
    try:
        import mss
        import PIL.Image
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(mon)
            return PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        pass

    # 3. PIL.ImageGrab
    try:
        import PIL.ImageGrab
        return PIL.ImageGrab.grab(all_screens=True).convert("RGB")
    except Exception:
        pass

    # 4. pyautogui
    try:
        if _PYAUTOGUI:
            return pyautogui.screenshot().convert("RGB")
    except Exception:
        pass

    return None


def _screenshot(save_path: str | None = None) -> str:
    path = _safe_screenshot_path(save_path)
    img  = _capture_screen_image()
    if img:
        img.save(str(path))
        return f"Screenshot saved: {path}"
    return "Failed to capture screenshot."


def _clear_field() -> str:
    _require_pyautogui()
    select_key = "command" if _get_os() == "mac" else "ctrl"
    pyautogui.hotkey(select_key, "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"

def _focus_window(title: str) -> str:
    os_name = _get_os()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=5, **_WIN_HIDE,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
        script = (
            f'tell application "System Events" to '
            f'set frontmost of (first process whose name contains "{title}") to true'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (macOS) failed: {e}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {title}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", title, "windowactivate"],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except FileNotFoundError:
            return "focus_window (Linux) requires wmctrl or xdotool"
        except Exception as e:
            return f"focus_window (Linux) failed: {e}"

    return f"focus_window: unknown OS '{os_name}'"

def _screen_find(description: str) -> tuple[int, int] | None:
    from core import gemini
    api_key = gemini.api_key() or _get_api_key()
    if not api_key:
        print("[ComputerControl] [!] No API key for screen_find")
        return None

    try:
        from google.genai import types as gtypes
        import PIL.Image

        _require_pyautogui()
        screen_w, screen_h = pyautogui.size()

        img = _capture_screen_image()
        if img is None:
            print("[ComputerControl] [!] Could not capture screen for screen_find")
            return None

        orig_w, orig_h = img.size

        # Downscale copy for fast upload & low network latency
        im_send = img.copy()
        im_send.thumbnail((1280, 720), PIL.Image.Resampling.BILINEAR)
        send_w, send_h = im_send.size

        scale_x = orig_w / float(send_w)
        scale_y = orig_h / float(send_h)

        buf = io.BytesIO()
        im_send.save(buf, format="JPEG", quality=85)
        image_bytes = buf.getvalue()

        prompt = (
            f"You are an expert GUI visual grounding agent. Locate the UI element on this screen matching: '{description}'.\n"
            f"Rules:\n"
            f"1. Accurately identify the bounding box enclosing '{description}' (button, video thumbnail/title, search box, link, chat/contact, icon, or menu item).\n"
            f"2. Return ONLY the bounding box in normalized [0, 1000] format: [ymin, xmin, ymax, xmax]\n"
            f"   Example: [420, 310, 480, 550]\n"
            f"3. Do NOT output any markdown, explanations, or words. Output ONLY the bracketed box [ymin, xmin, ymax, xmax].\n"
            f"4. If the target element is definitely not visible anywhere on screen, reply ONLY: NOT_FOUND"
        )

        client = gemini.client(timeout_ms=15000, key=api_key)
        vision_models = (
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
        )

        resp_text = ""
        for model_name in vision_models:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[
                        gtypes.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt
                    ]
                )
                if resp and resp.text:
                    resp_text = resp.text.strip()
                    if resp_text:
                        break
            except Exception as me:
                print(f"[ComputerControl] Vision model {model_name} warning: {me}")

        if not resp_text or "NOT_FOUND" in resp_text.upper():
            print(f"[ComputerControl] Element '{description}' not found by vision model")
            return None

        # 1. Parse standard box_2d [ymin, xmin, ymax, xmax] on normalized 0-1000 scale
        box_m = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', resp_text)
        if box_m:
            y1, x1, y2, x2 = map(float, box_m.groups())
            norm_x = (x1 + x2) / 2000.0
            norm_y = (y1 + y2) / 2000.0
            py_x = int(round(norm_x * screen_w))
            py_y = int(round(norm_y * screen_h))
            py_x = max(0, min(screen_w - 1, py_x))
            py_y = max(0, min(screen_h - 1, py_y))
            print(f"[ComputerControl] Found '{description}' box [{int(y1)},{int(x1)},{int(y2)},{int(x2)}] -> center ({py_x}, {py_y}) (screen {screen_w}x{screen_h})")
            return py_x, py_y

        # 2. Fallback point search
        pt_m = re.search(r'(\d+)\s*,\s*(\d+)', resp_text)
        if pt_m:
            v1, v2 = float(pt_m.group(1)), float(pt_m.group(2))
            if v1 <= 1000 and v2 <= 1000:
                py_x = int(round((v1 / 1000.0) * screen_w))
                py_y = int(round((v2 / 1000.0) * screen_h))
            else:
                py_x = int(round(v1 * (screen_w / float(orig_w))))
                py_y = int(round(v2 * (screen_h / float(orig_h))))
            py_x = max(0, min(screen_w - 1, py_x))
            py_y = max(0, min(screen_h - 1, py_y))
            print(f"[ComputerControl] Found '{description}' point -> ({py_x}, {py_y})")
            return py_x, py_y

    except Exception as e:
        print(f"[ComputerControl] screen_find failed: {e}")

    return None

def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for all computer control actions.

    parameters keys (all optional unless noted):
      action        : (required) one of the actions listed below
      text          : text to type or paste
      x, y          : screen coordinates
      button        : 'left' | 'right' (default: left)
      keys          : hotkey string, e.g. 'ctrl+c'
      key           : single key name, e.g. 'enter'
      direction     : 'up' | 'down' | 'left' | 'right'
      amount        : scroll amount (default: 3)
      seconds       : wait duration
      title         : window title fragment for focus_window
      description   : natural-language element description for screen_find/click
      type          : data type for random_data
      field         : memory field name for user_data
      clear_first   : bool, clear field before typing (default: true)
      path          : save path for screenshot (must be inside home dir)

    Actions:
      type          — type text at cursor
      smart_type    — clear field + type (clipboard-backed)
      click         — left click
      double_click  — double left click
      right_click   — right click
      move          — move mouse
      drag          — click-drag between two points
      hotkey        — key combination
      press         — single key
      scroll        — scroll the wheel
      copy          — read clipboard
      paste         — write + paste clipboard
      screenshot    — capture screen (safe path only)
      wait          — sleep N seconds
      clear_field   — select-all + delete
      focus_window  — bring window to foreground
      screen_find   — AI element finder (returns x,y)
      screen_click  — AI element finder + click
      random_data   — generate fake form data
      user_data     — pull real data from memory
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {params}")

    try:

        if action == "type":
            return _type(params.get("text", ""))

        if action == "smart_type":
            return _smart_type(
                params.get("text", ""),
                clear_first=params.get("clear_first", True),
            )

        if action in ("click", "left_click"):
            desc = params.get("description", "")
            if desc:
                coords = _screen_find(desc)
                if coords:
                    time.sleep(0.15)
                    _move(coords[0], coords[1], duration=0.2)
                    time.sleep(0.08)
                    _click(x=coords[0], y=coords[1], button="left", clicks=1)
                    return f"Successfully clicked '{desc}' at coordinates ({coords[0]}, {coords[1]})."
                return f"[FAILED] Element '{desc}' was not found on screen."
            return _click(params.get("x"), params.get("y"), "left", 1)

        if action in ("double_click", "screen_double_click"):
            desc = params.get("description", "")
            if desc:
                coords = _screen_find(desc)
                if coords:
                    time.sleep(0.15)
                    _move(coords[0], coords[1], duration=0.2)
                    time.sleep(0.08)
                    _click(x=coords[0], y=coords[1], button="left", clicks=2)
                    return f"Successfully double-clicked '{desc}' at coordinates ({coords[0]}, {coords[1]})."
                return f"[FAILED] Element '{desc}' was not found on screen for double-click."
            return _click(params.get("x"), params.get("y"), "left", 2)

        if action in ("right_click", "screen_right_click"):
            desc = params.get("description", "")
            if desc:
                coords = _screen_find(desc)
                if coords:
                    time.sleep(0.15)
                    _move(coords[0], coords[1], duration=0.2)
                    time.sleep(0.08)
                    _click(x=coords[0], y=coords[1], button="right", clicks=1)
                    return f"Successfully right-clicked '{desc}' at coordinates ({coords[0]}, {coords[1]})."
                return f"[FAILED] Element '{desc}' was not found on screen for right-click."
            return _click(params.get("x"), params.get("y"), "right", 1)

        if action in ("hover", "mouse_over"):
            desc = params.get("description", "")
            if desc:
                coords = _screen_find(desc)
                if coords:
                    time.sleep(0.15)
                    _move(coords[0], coords[1], duration=0.2)
                    return f"Moved mouse over '{desc}' at coordinates ({coords[0]}, {coords[1]})."
                return f"[FAILED] Element '{desc}' was not found on screen to hover."
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "drag":
            return _drag(
                int(params.get("x1", 0)), int(params.get("y1", 0)),
                int(params.get("x2", 0)), int(params.get("y2", 0)),
            )

        if action == "hotkey":
            raw  = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            return _hotkey(*keys)

        if action == "press":
            return _press(params.get("key", "enter"))

        if action == "scroll":
            return _scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
            )

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            return _clipboard_paste(params.get("text", ""))

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            desc   = params.get("description", "")
            if not desc:
                return "[FAILED] No element description provided for screen_click."
            coords = _screen_find(desc)
            if coords:
                time.sleep(0.15)
                _move(coords[0], coords[1], duration=0.2)
                time.sleep(0.08)
                _click(x=coords[0], y=coords[1])
                return f"Successfully clicked '{desc}' at coordinates ({coords[0]}, {coords[1]})."
            return f"[FAILED] Element '{desc}' was not found on screen. It might be off-screen, minimized, covered by another window, or still loading."

        if action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = min(secs, 30.0)
            time.sleep(secs)
            return f"Waited {secs}s"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 random {dt} → {result}")
            return result

        if action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ⚠️ No '{field}' in memory, using random: {value}")
            return value

        return f"Unknown action: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "computer_control",
    "description": "Direct computer control: type, click, right_click, double_click, hover, hotkeys, scroll, move mouse, screenshots, find and click elements on screen. Use action='screen_click', 'right_click', 'double_click', or 'hover' with 'description' to visually find and interact with any message, button, menu, video, tab, or UI element on screen.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "type | smart_type | click | double_click | right_click | hover | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"
            },
            "text": {
                "type": "STRING",
                "description": "Text to type or paste"
            },
            "x": {
                "type": "INTEGER",
                "description": "X coordinate"
            },
            "y": {
                "type": "INTEGER",
                "description": "Y coordinate"
            },
            "keys": {
                "type": "STRING",
                "description": "Key combination e.g. 'ctrl+c'"
            },
            "key": {
                "type": "STRING",
                "description": "Single key e.g. 'enter'"
            },
            "direction": {
                "type": "STRING",
                "description": "up | down | left | right"
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount (default: 3)"
            },
            "seconds": {
                "type": "NUMBER",
                "description": "Seconds to wait"
            },
            "title": {
                "type": "STRING",
                "description": "Window title for focus_window"
            },
            "description": {
                "type": "STRING",
                "description": "Description of the element, video, thumbnail, button, or link to find or click on screen."
            },
            "type": {
                "type": "STRING",
                "description": "Data type for random_data"
            },
            "field": {
                "type": "STRING",
                "description": "Field for user_data: name|email|city"
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)"
            },
            "path": {
                "type": "STRING",
                "description": "Save path for screenshot"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": computer_control,
}
