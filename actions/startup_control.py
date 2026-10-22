"""
Action: startup_control
Allows the user to enable, disable, toggle, or check whether Jarvis automatically
launches on PC boot / Windows startup.
"""
import os
import sys
import platform
from pathlib import Path

def startup_control(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "toggle").lower().strip()

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    win = None
    if app:
        for w in app.topLevelWidgets():
            if hasattr(w, "_check_autostart") and hasattr(w, "_toggle_autostart"):
                win = w
                break

    # Determine current status
    if win:
        current = win._check_autostart()
    else:
        current = _direct_check_autostart()

    if action in ("status", "check", "query"):
        status_str = "ENABLED (Jarvis automatically runs on PC startup)" if current else "DISABLED (Jarvis does NOT run on PC startup)"
        msg = f"PC startup auto-run is currently {status_str}."
        if player:
            player.write_log(f"[startup_control] {msg}")
        return msg

    target_on = None
    if action in ("enable", "on", "start", "activate"):
        target_on = True
    elif action in ("disable", "off", "stop", "deactivate"):
        target_on = False
    else:  # toggle
        target_on = not current

    if target_on == current:
        state_txt = "already ENABLED" if current else "already DISABLED"
        msg = f"PC startup auto-run is {state_txt}."
        if player:
            player.write_log(f"[startup_control] {msg}")
        return msg

    # Toggle through UI window if available
    if win:
        win._toggle_autostart()
        new_state = win._check_autostart()
    else:
        new_state = _direct_set_autostart(target_on)

    if new_state:
        msg = "PC startup auto-run has been ENABLED. Jarvis will start automatically when your PC turns on."
    else:
        msg = "PC startup auto-run has been DISABLED. Jarvis will no longer start automatically when your PC turns on."

    if player:
        player.write_log(f"[startup_control] {msg}")
    return msg


def _direct_check_autostart() -> bool:
    _os = platform.system()
    try:
        if _os == "Windows":
            import winreg
            found = False
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "JARVIS_AI")
                    found = True
                except FileNotFoundError:
                    found = False
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass
            if not found:
                startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                if startup_dir.exists() and any(startup_dir.glob("*jarvis*")):
                    found = True
            return found
        elif _os == "Darwin":
            return (Path.home() / "Library" / "LaunchAgents" / "com.jarvis.assistant.plist").exists()
        else:
            return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
    except Exception:
        return False


def _direct_set_autostart(enable: bool) -> bool:
    _os = platform.system()
    try:
        script = str(Path(__file__).resolve().parent.parent / "main.py")
        if _os == "Windows":
            import winreg
            reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            if not enable:
                try:
                    winreg.DeleteValue(reg, "JARVIS_AI")
                except FileNotFoundError:
                    pass
                try:
                    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                    if startup_dir.exists():
                        for f in startup_dir.glob("*jarvis*"):
                            f.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                pythonw = Path(sys.executable).parent / "pythonw.exe"
                exe = str(pythonw if pythonw.exists() else sys.executable)
                winreg.SetValueEx(reg, "JARVIS_AI", 0, winreg.REG_SZ, f'"{exe}" "{script}"')
            winreg.CloseKey(reg)
        elif _os == "Darwin":
            plist_dir = Path.home() / "Library" / "LaunchAgents"
            plist_dir.mkdir(parents=True, exist_ok=True)
            plist = plist_dir / "com.jarvis.assistant.plist"
            if not enable:
                plist.unlink(missing_ok=True)
            else:
                plist.write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                    '  <key>ProgramArguments</key><array>\n'
                    f'    <string>{sys.executable}</string>\n'
                    f'    <string>{script}</string>\n'
                    '  </array>\n'
                    '  <key>RunAtLoad</key><true/>\n'
                    '</dict></plist>\n'
                )
        else:
            desk_dir = Path.home() / ".config" / "autostart"
            desk_dir.mkdir(parents=True, exist_ok=True)
            desk = desk_dir / "jarvis.desktop"
            if not enable:
                desk.unlink(missing_ok=True)
            else:
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=JARVIS\n"
                    f"Exec={sys.executable} {script}\n"
                    "Type=Application\nTerminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n"
                )
        return enable
    except Exception:
        return False


TOOL = {
    "name": "startup_control",
    "description": (
        "Controls whether Jarvis runs automatically on PC boot / Windows startup. "
        "Use this tool when the user asks to enable, disable, turn off, or check startup behavior "
        "(e.g., 'startup band kardo', 'pc on hone par jarvis start mat hona', 'disable auto-start', 'turn on startup')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'enable' (turn on auto-start on PC boot) | 'disable' (turn off auto-start on PC boot) | 'status' (check current state) | 'toggle'"
            }
        },
        "required": ["action"]
    },
    "handler": startup_control,
}
