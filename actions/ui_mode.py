import sys

def ui_mode(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    raw_mode = params.get("mode", "toggle").lower().strip()

    target = "toggle"
    if any(w in raw_mode for w in ("face", "mini", "floating", "avatar", "compact", "sirf face")):
        target = "face"
    elif any(w in raw_mode for w in ("standard", "normal", "full", "hud", "sab dikhao")):
        target = "standard"

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if not app:
        return "[FAILED] UI application is not running."

    for w in app.topLevelWidgets():
        if hasattr(w, "toggle_display_mode"):
            res = w.toggle_display_mode(target if target != "toggle" else None)
            is_face = getattr(w, "_is_face_mode", False)
            if target == "face" or (target == "toggle" and is_face):
                msg = "Switched to Floating Face Mode (Always on Top). Only the animated face is visible now."
            else:
                msg = "Switched to Standard Full Mode. All panels, logs, and controls are visible."
            if player:
                player.write_log(f"[ui_mode] {msg}")
            return msg

    return "[FAILED] Could not locate Jarvis main window."


TOOL = {
    "name": "ui_mode",
    "description": "Switches the Jarvis display between 2 modes: 'face' (compact floating animated face on top of all windows) and 'standard' (full normal HUD with all panels and options). Use whenever the user asks to show only the face, switch to mini/floating mode, or return to normal/standard mode.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "description": "'face' (only floating animated face on top) | 'standard' (full normal HUD with all panels) | 'toggle'"
            }
        },
        "required": ["mode"]
    },
    "handler": ui_mode,
}
