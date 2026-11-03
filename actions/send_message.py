import json
import subprocess
import sys
import time
import threading
from pathlib import Path

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _get_active_window_title() -> str:
    """Returns the title of the current foreground window."""
    os_name = _get_os()
    if os_name == "windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    return buf.value
        except Exception:
            pass
    return ""


def _is_jarvis_window_active() -> bool:
    """Detects if Jarvis's own UI window is the active foreground window."""
    t = _get_active_window_title().lower()
    return any(k in t for k in ("jarvis", "j.a.r.v.i.s", "gemini assistant"))


def _is_whatsapp_window_active() -> bool:
    """Detects if WhatsApp window is currently the active foreground window."""
    t = _get_active_window_title().lower()
    return "whatsapp" in t


def _paste_text(text: str) -> bool:
    _require_pyautogui()

    # CRITICAL SAFEGUARD: Never type into Jarvis HUD!
    if _is_jarvis_window_active():
        print(f"[SendMessage] [CRITICAL GUARD] Blocked typing '{text[:25]}' because JARVIS HUD is focused!")
        return False

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)
    return True


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    if _is_jarvis_window_active():
        print("[SendMessage] [CRITICAL GUARD] Blocked clear_and_paste because JARVIS HUD is focused!")
        return
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)

def _is_app_running(app_name: str) -> bool:
    try:
        import psutil
        clean = app_name.lower().replace(".exe", "").strip()
        aliases = {
            "whatsapp": ["whatsapp", "whatsappdesktop"],
            "telegram": ["telegram"],
            "discord": ["discord"],
            "slack": ["slack"],
            "chrome": ["chrome"],
        }
        match_names = aliases.get(clean, [clean])
        for p in psutil.process_iter(['name']):
            p_name = (p.info.get('name') or '').lower()
            if any(m in p_name for m in match_names):
                return True
    except Exception:
        pass
    return False


def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            try:
                from actions.open_app import _launch_windows
                return _launch_windows(app_name)
            except Exception:
                pyautogui.press("win")
                time.sleep(0.5)
                _paste_text(app_name)
                time.sleep(0.6)
                pyautogui.press("enter")
                time.sleep(2.5)
                return _is_app_running(app_name)

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else: 
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched

    except Exception as e:
        print(f"[SendMessage] [!] Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0) 
        return True
    except Exception as e:
        print(f"[SendMessage] [!] Could not open browser: {e}")
        return False

def _search_in_app(query: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)

def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if not _open_app(app_name):
        return f"[FAILED] Could not open {app_name}. The app is not installed or failed to start."

    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."

def _activate_pc_whatsapp() -> bool:
    """Brings WhatsApp window to foreground on Windows and verifies focus."""
    os_name = _get_os()
    if os_name == "windows":
        # 1. PowerShell WScript.Shell AppActivate
        try:
            ps_cmd = '$ws = New-Object -ComObject WScript.Shell; if ($ws.AppActivate("WhatsApp")) { exit 0 } else { exit 1 }'
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, timeout=2.0,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            if res.returncode == 0:
                time.sleep(0.4)
                if _is_whatsapp_window_active():
                    return True
        except Exception:
            pass

        # 2. Win32 EnumWindows + SetForegroundWindow
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            found_hwnd = None

            def _enum_win(h, _):
                nonlocal found_hwnd
                if user32.IsWindowVisible(h):
                    length = user32.GetWindowTextLengthW(h)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buf, length + 1)
                        if "whatsapp" in buf.value.lower():
                            found_hwnd = h
                            return 0
                return 1

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_win), 0)

            if found_hwnd:
                SW_RESTORE = 9
                user32.ShowWindow(found_hwnd, SW_RESTORE)
                time.sleep(0.1)
                user32.SetForegroundWindow(found_hwnd)
                time.sleep(0.3)
                return True
        except Exception:
            pass

    return _is_whatsapp_window_active()


def _open_pc_whatsapp() -> bool:
    """Opens and focuses WhatsApp app on the PC, verifying it is active."""
    os_name = _get_os()
    if os_name == "windows":
        # 1. If already open and active, return True immediately
        if _activate_pc_whatsapp():
            return True

        # 2. Launch WhatsApp
        # Method A: Windows Store App AUMID
        try:
            subprocess.Popen(
                "explorer.exe shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
                shell=True
            )
        except Exception:
            pass

        # Method B: Protocol
        try:
            subprocess.Popen("start whatsapp:", shell=True)
        except Exception:
            pass

        # Wait for window to initialize
        for _ in range(8):
            time.sleep(0.4)
            if _activate_pc_whatsapp():
                return True

        # Method C: Start Menu search fallback
        try:
            pyautogui.press("win")
            time.sleep(0.4)
            pyautogui.write("WhatsApp", interval=0.03)
            time.sleep(0.5)
            pyautogui.press("enter")
            for _ in range(8):
                time.sleep(0.4)
                if _activate_pc_whatsapp():
                    return True
        except Exception:
            pass

        return _is_whatsapp_window_active()

    elif os_name == "mac":
        return _open_app("WhatsApp")
    else:
        return _open_app("whatsapp")


def _send_whatsapp_pc(receiver: str, message: str = "", action: str = "send") -> str:
    """
    Standard PC WhatsApp automation:
    1. Opens and focuses WhatsApp app on PC (with verification)
    2. Searches for contact (Ctrl + F)
    3. Opens their chat (Enter)
    4. Types message and sends (Enter)
    If PC WhatsApp cannot be focused, seamlessly falls back to Chrome WhatsApp Web!
    """
    _require_pyautogui()

    if not _open_pc_whatsapp():
        print("[SendMessage] PC WhatsApp could not be opened/focused. Falling back to Chrome WhatsApp Web...")
        return _send_whatsapp_chrome(receiver, message, action, fallback_from_pc=True)

    # CRITICAL SAFETY CHECK: Ensure Jarvis is NOT focused!
    if _is_jarvis_window_active() or not _is_whatsapp_window_active():
        print("[SendMessage] [SAFETY ABORT] Target window is not WhatsApp (Jarvis active). Falling back to Chrome...")
        return _send_whatsapp_chrome(receiver, message, action, fallback_from_pc=True)

    time.sleep(0.6)

    # 1. Focus search bar in WhatsApp
    os_name = _get_os()
    search_key = ("command", "f") if os_name == "mac" else ("ctrl", "f")
    pyautogui.hotkey(*search_key)
    time.sleep(0.4)

    # 2. Clear previous search and enter contact name
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.08)
    pyautogui.press("backspace")
    time.sleep(0.08)
    if not _paste_text(receiver):
        return "[FAILED] Could not paste contact name (Jarvis HUD was focused). Aborted."
    time.sleep(1.2)

    # 3. Open chat
    pyautogui.press("enter")
    time.sleep(0.8)

    # If user only wanted to open the chat:
    if action == "open_chat" or not message.strip():
        return f"WhatsApp chat with '{receiver}' is now open on PC."

    # 4. Type message and send
    if not _paste_text(message):
        return "[FAILED] Could not paste message text (Jarvis HUD was focused). Aborted."
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.4)
    return f"Message sent to {receiver} via WhatsApp."


def _send_whatsapp_chrome(receiver: str, message: str = "", action: str = "send", fallback_from_pc: bool = False) -> str:
    """
    Opens WhatsApp Web in Chrome and opens chat / sends message.
    Used when user specifically asks to send via Chrome or as a seamless fallback.
    """
    _require_pyautogui()
    from urllib.parse import quote_plus
    from actions.browser_control import _navigate_current_tab, _open_native

    prefix = "PC WhatsApp app open nahi ho saka, isliye " if fallback_from_pc else ""

    digits = "".join(c for c in receiver if c.isdigit() or c == "+")
    if len(digits) >= 10:
        clean_num = digits.lstrip("+")
        if message.strip():
            url = f"https://web.whatsapp.com/send?phone={clean_num}&text={quote_plus(message.strip())}"
        else:
            url = f"https://web.whatsapp.com/send?phone={clean_num}"
        if not _navigate_current_tab(url, "chrome"):
            _open_native(url, "chrome")
        return f"{prefix}Opened WhatsApp Web in Chrome for {receiver}."

    # Contact name search
    url = "https://web.whatsapp.com"
    if not _navigate_current_tab(url, "chrome"):
        _open_native(url, "chrome")
    time.sleep(3.5)

    # Ensure Chrome is focused before typing
    if _get_os() == "windows":
        try:
            ps_cmd = '$ws = New-Object -ComObject WScript.Shell; $ws.AppActivate("Chrome")'
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], timeout=1.5)
        except Exception:
            pass

    # Safety check: do not type into Jarvis!
    if _is_jarvis_window_active():
        return f"{prefix}[FAILED] Chrome window could not be focused. Please click on Chrome."

    # Search contact in WhatsApp Web (Ctrl+Alt+/)
    pyautogui.hotkey("ctrl", "alt", "/")
    time.sleep(0.6)
    _paste_text(receiver)
    time.sleep(1.2)
    pyautogui.press("enter")
    time.sleep(0.8)

    if action == "open_chat" or not message.strip():
        return f"{prefix}WhatsApp Web chat with '{receiver}' opened in Chrome."

    _paste_text(message)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.4)
    return f"{prefix}Message sent to {receiver} via WhatsApp Web in Chrome."


def _schedule_message_task(seconds: int, task_fn, *args):
    """Executes a message sending task in background after delay."""
    def _worker():
        print(f"[SendMessage] [Scheduled] Waiting {seconds}s before executing...")
        time.sleep(seconds)
        print(f"[SendMessage] [Scheduled] Delay expired. Executing message...")
        try:
            res = task_fn(*args)
            print(f"[SendMessage] [Scheduled] Result: {res}")
        except Exception as e:
            print(f"[SendMessage] [Scheduled] Error: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def _handle_telegram(receiver: str, message: str = "", action: str = "send") -> str:
    _require_pyautogui()
    if not _open_app("Telegram"):
        return "Could not open Telegram."
    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.6)
    if action == "open_chat" or not message.strip():
        return f"Telegram chat with '{receiver}' is now open."
    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via Telegram."


def _send_whatsapp(receiver: str, message: str) -> str:
    return _send_whatsapp_pc(receiver, message, action="send")

def _send_telegram(receiver: str, message: str) -> str:
    return _handle_telegram(receiver, message, action="send")

def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return "Could not open Instagram in browser."

    _paste_text(receiver)
    time.sleep(1.5)

    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")   
    time.sleep(0.4)

    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    if message.strip():
        _paste_text(message)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.3)
        return f"Message sent to {receiver} via Instagram."
    return f"Instagram chat with {receiver} is now open."


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."

    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    if message.strip():
        _paste_text(message)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.3)
        return f"Message sent to {receiver} via Messenger."
    return f"Messenger chat with {receiver} is now open."

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp),
    ({"telegram", "tg"},                      _send_telegram),
    ({"instagram", "ig", "insta"},            _send_instagram),
    ({"signal"},                               _send_signal),
    ({"discord"},                              _send_discord),
    ({"messenger", "facebook", "fb"},         _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params        = parameters or {}
    action        = params.get("action", "").lower().strip()
    receiver      = (params.get("receiver") or params.get("contact") or params.get("name") or "").strip()
    message_text  = (params.get("message_text") or params.get("message") or params.get("text") or "").strip()
    platform      = params.get("platform", "whatsapp").strip()
    via_chrome    = bool(params.get("via_chrome") or params.get("in_browser") or params.get("chrome"))
    delay_seconds = int(params.get("delay_seconds") or 0)
    delay_minutes = float(params.get("delay_minutes") or 0)
    if delay_minutes > 0 and delay_seconds == 0:
        delay_seconds = int(delay_minutes * 60)

    if not action:
        action = "send" if message_text else "open_chat"

    if not receiver:
        return "Please specify a recipient or contact name (e.g. 'Kunal')."

    if action == "send" and not message_text:
        action = "open_chat"

    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    desc = f"chat with {receiver}" if action == "open_chat" else f"{receiver}: {message_text[:40]}"
    print(f"[SendMessage] [msg] {platform} ({action}) -> {desc} [delay: {delay_seconds}s, via_chrome: {via_chrome}]")
    if player:
        player.write_log(f"[msg] {platform} -> {receiver}")

    # Handle Delayed/Scheduled message (e.g. "5 min baad ye msg bhej dena")
    if delay_seconds > 0:
        target_fn = _send_whatsapp_chrome if via_chrome else _send_whatsapp_pc
        _schedule_message_task(delay_seconds, target_fn, receiver, message_text, action)
        mins = delay_seconds // 60
        secs = delay_seconds % 60
        time_desc = f"{mins} minute" if mins and not secs else (f"{mins}m {secs}s" if mins else f"{secs} second")
        app_name = "Chrome me WhatsApp Web" if via_chrome else "WhatsApp"
        result = f"Theek hai, {time_desc} baad automatically {app_name} open karke {receiver} ko message bhej diya jayega."
        print(f"[SendMessage] [Scheduled] {result}")
        if player:
            player.write_log(f"[msg] Scheduled {time_desc}")
        return result

    try:
        plat_lower = platform.lower()
        if any(k in plat_lower for k in ("whatsapp", "wp", "wapp")):
            if via_chrome:
                result = _send_whatsapp_chrome(receiver, message_text, action)
            else:
                result = _send_whatsapp_pc(receiver, message_text, action)
        elif any(k in plat_lower for k in ("telegram", "tg")):
            result = _handle_telegram(receiver, message_text, action)
        else:
            handler = _resolve_platform(platform)
            result  = handler(receiver, message_text)
    except Exception as e:
        result = f"Could not complete messaging action: {e}"

    print(f"[SendMessage] Result: {result}")
    if player:
        player.write_log(f"[msg] {result[:60]}")

    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "send_message",
    "description": (
        "Sends a message or opens a contact's chat on WhatsApp (PC app or Chrome), Telegram, etc. "
        "By default, when user says 'WhatsApp pe isko msg bhejo', it opens PC WhatsApp, searches the contact, opens their chat, types the message, and sends it. "
        "If the user specifies 'Chrome me jake WhatsApp kholke msg bhejo', set via_chrome=true to use Chrome WhatsApp Web. "
        "If the user specifies sending after a delay (e.g. '5 min baad msg bhej dena'), set delay_seconds=300 (or delay in seconds)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {
                "type": "STRING",
                "description": "Recipient contact / person name (e.g. 'Kunal', 'Mom', 'Rahul') or phone number"
            },
            "message_text": {
                "type": "STRING",
                "description": "The message to send. Leave blank if only opening chat."
            },
            "action": {
                "type": "STRING",
                "description": "send | open_chat (default is send if message_text is provided, else open_chat)"
            },
            "via_chrome": {
                "type": "BOOLEAN",
                "description": "Set to true ONLY if the user specifically asked to use Chrome ('Chrome me jake WhatsApp kholke...'). Default is false (uses PC WhatsApp)."
            },
            "delay_seconds": {
                "type": "INTEGER",
                "description": "Delay in seconds before sending (e.g. 300 for 5 minutes). Use when the user says '5 min baad msg bhej dena'."
            },
            "platform": {
                "type": "STRING",
                "description": "Platform: WhatsApp, Telegram, Instagram, Signal, Discord, Messenger (default: WhatsApp)"
            }
        },
        "required": [
            "receiver"
        ]
    },
    "handler": send_message,
}

