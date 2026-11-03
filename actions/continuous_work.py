"""
actions/continuous_work.py
Continuous Autonomous Work & Cognitive Goal Execution Engine for JARVIS.

Provides a generalized, low-latency autonomous loop that perceives the desktop screen,
reasons about multi-step user intents, executes keyboard/mouse/speech actions, visually
verifies outcomes, and proactively asks the user for clarification if obstacles or
ambiguities arise.

Key Capabilities:
1. 'autonomous_goal': Generalized autonomous perception-action loop for ANY multi-step
   desktop goal (forms, documents, repetitive workflows, media control, verification).
   Analyzes the screen in real-time, plans the next action, executes, verifies, and
   persists until completion.
2. 'present_slides': High-speed, verified presentation specialist for PowerPoint, PDF,
   and Google Slides. Reads and explains slides linewise in natural, polite Hindi,
   delivers presentation speech, and advances with instant multi-method visual verification.
3. 'watch_and_act': Low-latency screen watcher that periodically looks for a target
   button or UI element (e.g. "Skip Ad", "Next", "Continue") and triggers actions.
4. 'monitor_goal': Observes screen progress for long processes (downloads, installations)
   and alerts the user upon completion.
5. 'status': Reports active continuous task state and progress.
6. 'stop': Immediately halts any running continuous task.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import math
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

# Ensure console output doesn't crash on Windows charmap (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

try:
    import pyautogui
    pyautogui.FAILSAFE = False
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
    _PIL = True
except ImportError:
    _PIL = False

try:
    import mss
    _MSS = True
except ImportError:
    _MSS = False


# -- Global Task State & Human-In-The-Loop Channels ----------------------------

_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()
_USER_FEEDBACK_EVENT = threading.Event()
_USER_FEEDBACK: Optional[str] = None
_WORKER_THREAD: Optional[threading.Thread] = None

_TASK_STATE = {
    "active": False,
    "mode": None,
    "target": None,
    "goal": None,
    "cycles": 0,
    "triggers": 0,
    "start_time": 0.0,
    "last_check": 0.0,
    "status_msg": "Idle",
    "waiting_for_user": False,
    "last_question": None,
}


def is_active() -> bool:
    with _LOCK:
        return _TASK_STATE["active"]


def is_waiting_for_user() -> bool:
    with _LOCK:
        return _TASK_STATE["waiting_for_user"]


def get_status() -> dict:
    with _LOCK:
        return dict(_TASK_STATE)


def stop_continuous_work() -> str:
    global _WORKER_THREAD
    with _LOCK:
        if not _TASK_STATE["active"]:
            return "No continuous task is currently active."
        _STOP_EVENT.set()
        _USER_FEEDBACK_EVENT.set()
        _TASK_STATE["active"] = False
        _TASK_STATE["waiting_for_user"] = False
        _TASK_STATE["status_msg"] = "Stopped by user"

    print("[ContinuousWork] [STOP] Continuous work stopped by user request.")
    return "Continuous work stopped successfully."


def submit_user_feedback(feedback_text: str) -> bool:
    """Delivers user speech or text input directly to the active autonomous loop."""
    global _USER_FEEDBACK
    with _LOCK:
        if not _TASK_STATE["active"]:
            return False
        _USER_FEEDBACK = feedback_text.strip()
        _TASK_STATE["waiting_for_user"] = False
        _USER_FEEDBACK_EVENT.set()
        print(f"[ContinuousWork] [USER_FEEDBACK] Received: {_USER_FEEDBACK}")
        return True


# -- Ultra-Fast Screen Capture & Low-Latency Vision Prep ------------------------

def _ensure_input_desktop() -> None:
    """Ensures the current thread is attached to the interactive user desktop."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
                user32.CloseDesktop(hdesk)
        except Exception:
            pass


def _capture_screen_img() -> Optional[PIL.Image.Image]:
    """Capture current desktop screen with sub-25ms native Windows GDI BitBlt attached to input desktop."""
    _ensure_input_desktop()

    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            if w > 0 and h > 0:
                hdc_screen = user32.GetDC(0)
                hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
                old_bm = gdi32.SelectObject(hdc_mem, hbm)

                # Pure SRCCOPY without CAPTUREBLT crash
                SRCCOPY = 0x00CC0020
                gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, SRCCOPY)
                # Unselect bitmap before GetDIBits
                gdi32.SelectObject(hdc_mem, old_bm)

                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wintypes.DWORD),
                        ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD),
                    ]

                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = w
                bmi.biHeight = -h
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0

                buf = ctypes.create_string_buffer(w * h * 4)
                gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

                gdi32.DeleteObject(hbm)
                gdi32.DeleteDC(hdc_mem)
                user32.ReleaseDC(0, hdc_screen)

                img = PIL.Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
                # Sanity check extrema - if completely black, try fallbacks
                if img.getextrema() != ((0, 0), (0, 0), (0, 0)):
                    return img
        except Exception:
            pass

    # Fallback 1: MSS
    if _MSS:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                return PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            pass

    # Fallback 2: PIL ImageGrab
    if _PIL:
        try:
            return PIL.ImageGrab.grab().convert("RGB")
        except Exception:
            pass

    # Fallback 3: PyAutoGUI
    if _PYAUTOGUI:
        try:
            return pyautogui.screenshot().convert("RGB")
        except Exception:
            pass

    return None


def _compress_for_vision(img: PIL.Image.Image, max_dim: int = 960) -> bytes:
    """Downscale and compress screenshot to lightweight JPEG (~15-40KB) for instant upload."""
    im = img.copy()
    im.thumbnail((max_dim, max_dim), PIL.Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=68, optimize=False)
    return buf.getvalue()


# -- Fast Difference & Verification --------------------------------------------

def _image_hash(img: PIL.Image.Image) -> str:
    """Fast 16x16 perceptual thumbnail hash to compare consecutive screen states."""
    try:
        small = img.resize((16, 16), PIL.Image.Resampling.BILINEAR).convert("L")
        pixels = list(small.tobytes())
        avg = sum(pixels) / float(len(pixels))
        return "".join("1" if p > avg else "0" for p in pixels)
    except Exception:
        return ""


def _hash_distance(h1: str, h2: str) -> int:
    if not h1 or not h2 or len(h1) != len(h2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def _screen_difference_metric(img1: PIL.Image.Image, img2: PIL.Image.Image) -> float:
    """Returns normalized pixel difference [0.0 to 1.0] between two screen captures."""
    try:
        t1 = img1.resize((64, 64), PIL.Image.Resampling.BILINEAR).convert("L")
        t2 = img2.resize((64, 64), PIL.Image.Resampling.BILINEAR).convert("L")
        b1 = t1.tobytes()
        b2 = t2.tobytes()
        return sum(abs(a - b) for a, b in zip(b1, b2)) / (64 * 64 * 255.0)
    except Exception:
        return 0.0


def _has_screen_changed(
    img_before: PIL.Image.Image,
    img_after: PIL.Image.Image,
    target_box: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    """Verifies whether screen visually changed after an action globally or locally."""
    if not img_before or not img_after:
        return False

    # Check local box difference if target was a localized click
    if target_box:
        try:
            x1, y1, x2, y2 = target_box
            w, h = img_before.size
            # Clamp with padding
            bx1 = max(0, min(x1, x2) - 20)
            by1 = max(0, min(y1, y2) - 20)
            bx2 = min(w, max(x1, x2) + 20)
            by2 = min(h, max(y1, y2) + 20)
            if (bx2 - bx1) > 10 and (by2 - by1) > 10:
                crop1 = img_before.crop((bx1, by1, bx2, by2))
                crop2 = img_after.crop((bx1, by1, bx2, by2))
                local_diff = _screen_difference_metric(crop1, crop2)
                if local_diff > 0.015:
                    return True
        except Exception:
            pass

    # Global difference check
    diff = _screen_difference_metric(img_before, img_after)
    h_dist = _hash_distance(_image_hash(img_before), _image_hash(img_after))
    return diff >= 0.008 or h_dist >= 4


# -- Reliable Native Windows & PyAutoGUI Input Automation ----------------------

_VK_MAP = {
    "right": 0x27,
    "left": 0x25,
    "up": 0x26,
    "down": 0x28,
    "pagedown": 0x22,
    "pageup": 0x21,
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "f5": 0x74,
}


def _press_key_native(key_name: str) -> bool:
    """Press keyboard key via Win32 keybd_event and PyAutoGUI fallback."""
    k = key_name.lower().strip()
    if sys.platform == "win32":
        vk = _VK_MAP.get(k)
        if vk:
            try:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                return True
            except Exception:
                pass

    if _PYAUTOGUI:
        try:
            pyautogui.press(k)
            return True
        except Exception:
            pass

    return False


def _type_text_native(text: str) -> bool:
    """Fast text input via clipboard paste or pyautogui."""
    if not text:
        return False
    if _PYPERCLIP:
        try:
            pyperclip.copy(text)
            time.sleep(0.04)
            if _PYAUTOGUI:
                pyautogui.hotkey("ctrl", "v")
            elif sys.platform == "win32":
                # Send Ctrl+V
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0) # VK_CONTROL
                ctypes.windll.user32.keybd_event(0x56, 0, 0, 0) # 'V'
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
            return True
        except Exception:
            pass

    if _PYAUTOGUI:
        try:
            pyautogui.write(text, interval=0.01)
            return True
        except Exception:
            pass

    return False


def _click_coords_native(x: int, y: int, button: str = "left", double: bool = False) -> bool:
    """Perform mouse click at coordinates using native Win32 or PyAutoGUI."""
    if _PYAUTOGUI:
        try:
            if double:
                pyautogui.doubleClick(x, y)
            elif button == "right":
                pyautogui.rightClick(x, y)
            else:
                pyautogui.click(x, y)
            return True
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            user32.SetCursorPos(x, y)
            time.sleep(0.03)
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            MOUSEEVENTF_RIGHTDOWN = 0x0008
            MOUSEEVENTF_RIGHTUP = 0x0010

            down = MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_LEFTDOWN
            up = MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_LEFTUP

            user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(up, 0, 0, 0, 0)

            if double:
                time.sleep(0.06)
                user32.mouse_event(down, 0, 0, 0, 0)
                time.sleep(0.03)
                user32.mouse_event(up, 0, 0, 0, 0)
            return True
        except Exception:
            pass

    return False


def _scroll_native(amount: int) -> bool:
    """Scroll mouse wheel natively."""
    if _PYAUTOGUI:
        try:
            pyautogui.scroll(amount)
            return True
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            MOUSEEVENTF_WHEEL = 0x0800
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount, 0)
            return True
        except Exception:
            pass

    return False


def _activate_presentation_window() -> bool:
    """Fast, single-shot foreground activation for presentation / document viewers."""
    if sys.platform == "win32":
        try:
            ps_cmd = '$ws = New-Object -ComObject WScript.Shell; $cands = @("Edge", "Chrome", "Acrobat", "Reader", "PDF", "PowerPoint", "Slide Show", "Presentation", "Blackbook"); foreach ($c in $cands) { if ($ws.AppActivate($c)) { exit 0 } }; exit 1'
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                timeout=0.5,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return res.returncode == 0
        except Exception:
            pass
    return False


# -- Dynamic Speech Monitoring (Snappy & Zero Latency) -------------------------

def _wait_for_speech_to_finish(player, text: str, max_wait: float = 8.0) -> None:
    """Dynamically monitors speech activity and returns immediately when speaking stops."""
    if not text:
        return

    words = len(text.split())
    # Generous minimum expected speech duration
    min_listen_time = max(0.8, min(6.0, (words / 3.0)))
    t0 = time.time()

    time.sleep(0.1)

    while (time.time() - t0) < max_wait and not _STOP_EVENT.is_set():
        is_spk = False
        if player and hasattr(player, "is_speaking"):
            try:
                is_spk = player.is_speaking()
            except Exception:
                pass
        elif player and hasattr(player, "_win") and hasattr(player._win, "hud"):
            try:
                is_spk = getattr(player._win.hud, "speaking", False)
            except Exception:
                pass

        elapsed = time.time() - t0
        if not is_spk and elapsed >= min_listen_time:
            break

        time.sleep(0.06)


# -- Human-In-The-Loop Clarification Engine -----------------------------------

def _ask_user_and_wait(
    question: str,
    timeout: float = 35.0,
    player=None,
    speak_func=None,
) -> Optional[str]:
    """Asks the user a spoken question in Hindi and pauses until user answers or times out."""
    global _USER_FEEDBACK, _TASK_STATE

    with _LOCK:
        _USER_FEEDBACK = None
        _USER_FEEDBACK_EVENT.clear()
        _TASK_STATE["waiting_for_user"] = True
        _TASK_STATE["last_question"] = question
        _TASK_STATE["status_msg"] = f"Waiting for user input: {question[:45]}..."

    print(f"[ContinuousWork] [HUMAN_IN_THE_LOOP] Asking user: {question}")
    if player:
        player.write_log(f"[Jarvis Clarification] {question}")

    if speak_func:
        directive = f"[SYSTEM INSTRUCTION: ASK USER DIRECTLY IN POLITE HINDI]: {question}"
        speak_func(directive)
        _wait_for_speech_to_finish(player, question, max_wait=6.0)

    # Wait for user reply event
    t0 = time.time()
    while (time.time() - t0) < timeout and not _STOP_EVENT.is_set():
        if _USER_FEEDBACK_EVENT.wait(timeout=0.2):
            with _LOCK:
                _TASK_STATE["waiting_for_user"] = False
                ans = _USER_FEEDBACK
                _USER_FEEDBACK = None
                return ans

    with _LOCK:
        _TASK_STATE["waiting_for_user"] = False
    return None


# -- Engine 1: Generalized Autonomous Perception-Action Goal Loop --------------

def _run_autonomous_goal(
    goal_description: str,
    interval: float,
    max_cycles: int,
    player,
    speak_func,
    session_memory=None,
):
    """High-speed Autonomous Perception-Action Engine for multi-step desktop tasks."""
    global _TASK_STATE
    from core import gemini
    from google.genai import types as gtypes

    cycles = 0
    history = []
    answered_items = []
    recent_clicks = []
    consecutive_scrolls = 0
    preferred_method_holder = {"method": None}

    # Format previous session conversation turns
    session_context = "No previous chat history available."
    if session_memory and isinstance(session_memory, (list, tuple)):
        clean_turns = [str(t).strip() for t in session_memory if str(t).strip()]
        if clean_turns:
            session_context = "\n".join(clean_turns[-8:])

    print(f"[ContinuousWork] [START] Autonomous Goal Engine started for: '{goal_description}'")
    if player:
        player.write_log(f"[Autonomous Goal] Starting: '{goal_description}'")

    time.sleep(0.15)

    while not _STOP_EVENT.is_set() and cycles < max_cycles:
        cycles += 1
        with _LOCK:
            _TASK_STATE["cycles"] = cycles
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Cycle {cycles}: Analyzing screen..."

        img = _capture_screen_img()
        if not img or _STOP_EVENT.is_set():
            time.sleep(0.1)
            continue

        screen_w, screen_h = img.size
        img_bytes = _compress_for_vision(img, max_dim=960)

        history_summary = "\n".join(history[-5:]) if history else "Task just started."
        answered_summary = "\n".join(f"- {it}" for it in answered_items[-20:]) if answered_items else "None yet."

        prompt = (
            f"You are the high-speed autonomous execution agent for JARVIS.\n"
            f"User Goal / Intent: '{goal_description}'.\n"
            f"Cycle: {cycles}/{max_cycles}.\n\n"
            f"Recent Conversation with User (Context):\n{session_context}\n\n"
            f"Completed / Answered Items So Far ({len(answered_items)}):\n{answered_summary}\n\n"
            f"Recent Action History (Last 5 steps):\n{history_summary}\n\n"
            "Examine the attached desktop screen carefully to understand the current state vs the user's goal.\n"
            "Determine the exact next action to make progress toward completing the goal.\n\n"
            "MANDATORY EXECUTION RULES:\n"
            "1. Quizzes, Questionnaires, Web Forms & Surveys (CRITICAL):\n"
            "   - Carefully examine EVERY question visible on screen right now.\n"
            "   - Check if visible questions ALREADY have an answer selected (e.g. radio button filled, checkbox checked, dropdown chosen, or listed in 'Completed / Answered Items').\n"
            "   - NEVER re-answer or re-click an already-answered question! Doing so is a major failure.\n"
            "   - If an UNANSWERED question is visible: click the correct/best option radio button or text for THAT unanswered question. Record the question and selected answer in 'answered_item_now'.\n"
            "   - MANDATORY AUTO-SCROLL DOWN: If ALL questions currently visible on screen are ALREADY answered, you MUST NOT click any of them again! Your action MUST be:\n"
            "     action: {\"type\": \"scroll\", \"scroll_amount\": -450}\n"
            "     Set visible_questions_status='all_visible_answered_need_scroll'. Scroll down to reveal subsequent unattempted questions!\n"
            "   - CHECK FOR MISSED QUESTIONS BEFORE SUBMITTING: If you reach the bottom of the page (e.g. 'Submit', 'Next Page', 'Finish' button is visible), review the whole form/page: did you miss or skip any question? If any question was missed or left blank, scroll back up (action: {\"type\": \"scroll\", \"scroll_amount\": 450}) to locate and answer it before submitting! Only click submit when all questions are verified complete.\n"
            "2. Presentation or Document (PDF / PPT / Web Slides):\n"
            "   - Read and explain visible page content in polite, natural Hindi in 'speech'.\n"
            "   - Action: 'key' with target 'pagedown' or 'right' to advance to the next page.\n"
            "   - If on conclusion/final page, set goal_status='completed' and action 'done'.\n"
            "3. General Clicking / Form Filling:\n"
            "   - Action: 'click' with 'box_2d': [ymin, xmin, ymax, xmax] in normalized [0, 1000] coordinates.\n"
            "   - Action: 'type' with 'box_2d' of field and 'text' to type.\n"
            "   - Keep 'speech': '' during mechanical clicks/types to avoid unnecessary audio delay.\n"
            "4. Human-In-The-Loop Clarification:\n"
            "   - If an unexpected error, ambiguous prompt, or missing information blocks progress, set action 'ask_user' and provide Hindi 'question'.\n"
            "5. Goal Completed:\n"
            "   - When all questions, form fields, or tasks are fully verified complete, set goal_status='completed', action 'done', and give brief Hindi confirmation in 'speech'.\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "observation": "Brief 1-sentence description of visible screen state (which questions are visible & their answer status)",\n'
            '  "thought": "1-sentence reasoning for next step",\n'
            '  "visible_questions_status": "has_unanswered" | "all_visible_answered_need_scroll" | "page_end_check_submit",\n'
            '  "answered_item_now": "Question snippet and selected answer if answered this turn, else null",\n'
            '  "goal_status": "in_progress" | "completed" | "needs_user_input",\n'
            '  "speech": "Hindi speech if reading/explaining/confirming, or empty string",\n'
            '  "action": {\n'
            '    "type": "click" | "scroll" | "type" | "key" | "ask_user" | "done",\n'
            '    "target": "pagedown" | "right" | "enter" | "tab" | "down",\n'
            '    "box_2d": [ymin, xmin, ymax, xmax],\n'
            '    "text": "text to type if type action",\n'
            '    "scroll_amount": -450,\n'
            '    "question": "Hindi question if ask_user"\n'
            "  }\n"
            "}\n"
            "Emit ONLY valid JSON."
        )

        try:
            part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=8000)
        except Exception as e:
            print(f"[ContinuousWork] Vision call exception: {e}")
            time.sleep(0.3)
            continue

        if not resp or not getattr(resp, "text", ""):
            time.sleep(0.2)
            continue

        raw = resp.text.strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

        try:
            decision = json.loads(raw)
        except Exception as e:
            print(f"[ContinuousWork] JSON parse error: {e}")
            time.sleep(0.2)
            continue

        obs = decision.get("observation", "")
        thought = decision.get("thought", "")
        goal_status = decision.get("goal_status", "in_progress")
        vis_status = decision.get("visible_questions_status", "has_unanswered")
        answered_now = decision.get("answered_item_now")
        speech_text = decision.get("speech", "").strip()
        act_info = decision.get("action") or {}
        act_type = act_info.get("type", "wait").lower().strip()

        if answered_now and isinstance(answered_now, str) and answered_now.strip():
            ans_clean = answered_now.strip()
            if ans_clean not in answered_items:
                answered_items.append(ans_clean)
                print(f"[ContinuousWork] [QUESTION_ANSWERED] {ans_clean}")
                if player:
                    player.write_log(f"[Quiz/Form] Completed: {ans_clean[:45]}")

        print(f"[ContinuousWork] [CYCLE {cycles}] Obs: {obs} | Thought: {thought} | Action: {act_type}")
        if player and obs:
            player.write_log(f"[Autonomous Agent] {obs}")

        # 1. Spoken Presentation / Status delivery
        if speech_text and speak_func and not _STOP_EVENT.is_set():
            directive = f"[SYSTEM INSTRUCTION: SPEAK DIRECTLY IN POLITE NATURAL HINDI]: {speech_text}"
            speak_func(directive)
            _wait_for_speech_to_finish(player, speech_text, max_wait=8.0)

        # 2. Check for completion
        if goal_status == "completed" or act_type == "done":
            print(f"[ContinuousWork] [DONE] Goal completed: {goal_description}")
            if player:
                player.write_log(f"[Autonomous Agent] Goal completed: {goal_description}")
            if speak_func and not speech_text:
                speak_func("Sir, aapka task poori tarah complete ho gaya hai.")
            break

        # 3. Check for Human-In-The-Loop Clarification
        if act_type == "ask_user" or goal_status == "needs_user_input":
            question = act_info.get("question") or "Sir, aage proceed karne ke liye aapka confirmation chahiye."
            user_reply = _ask_user_and_wait(question, timeout=30.0, player=player, speak_func=speak_func)
            if user_reply:
                history.append(f"Cycle {cycles}: Asked user '{question}', user replied: '{user_reply}'.")
            else:
                history.append(f"Cycle {cycles}: Asked user '{question}', received no response.")
            continue

        # 4. Deterministic Anti-Loop Guard: Intercept repetitive clicks & auto-scroll
        action_executed = False
        action_desc = ""
        target_box_px: Optional[Tuple[int, int, int, int]] = None

        if act_type in ("click", "double_click", "right_click"):
            box = act_info.get("box_2d") or act_info.get("coords")
            if box and len(box) >= 4:
                y1, x1, y2, x2 = box[:4]
                cx = int(round(((x1 + x2) / 2000.0) * screen_w))
                cy = int(round(((y1 + y2) / 2000.0) * screen_h))
                target_box_px = (int(x1 * screen_w / 1000.0), int(y1 * screen_h / 1000.0),
                                 int(x2 * screen_w / 1000.0), int(y2 * screen_h / 1000.0))
            elif box and len(box) == 2:
                cx = int(round((box[0] / 1000.0) * screen_w)) if box[0] <= 1000 else int(box[0])
                cy = int(round((box[1] / 1000.0) * screen_h)) if box[1] <= 1000 else int(box[1])
                target_box_px = (cx - 15, cy - 15, cx + 15, cy + 15)
            else:
                cx, cy = screen_w // 2, screen_h // 2

            # Check if this click target was already clicked recently or all questions answered
            is_repeated_click = any(math.hypot(cx - px, cy - py) < 28 for px, py in recent_clicks[-3:])
            all_answered = (vis_status == "all_visible_answered_need_scroll")

            if is_repeated_click or all_answered:
                print(f"[ContinuousWork] [ANTI-LOOP TRIGGERED] Click at ({cx}, {cy}) is repeated or visible questions already answered. Overriding action to scroll down!")
                if player:
                    player.write_log("[Autonomous Agent] Visible questions already answered. Scrolling down for next questions...")
                act_type = "scroll"
                act_info = {"type": "scroll", "scroll_amount": -450}
            else:
                recent_clicks.append((cx, cy))
                if len(recent_clicks) > 8:
                    recent_clicks.pop(0)

        # 5. Execute Action
        if act_type == "key":
            key_name = act_info.get("target") or "pagedown"
            _activate_presentation_window()
            _press_key_native(key_name)
            action_executed = True
            action_desc = f"Pressed key '{key_name}'"
            consecutive_scrolls = 0

        elif act_type in ("click", "double_click", "right_click"):
            double = (act_type == "double_click")
            btn = "right" if act_type == "right_click" else "left"
            _click_coords_native(cx, cy, button=btn, double=double)
            action_executed = True
            action_desc = f"Clicked at ({cx}, {cy})"
            consecutive_scrolls = 0

        elif act_type == "type":
            box = act_info.get("box_2d") or act_info.get("coords")
            if box and len(box) >= 4:
                y1, x1, y2, x2 = box[:4]
                cx = int(round(((x1 + x2) / 2000.0) * screen_w))
                cy = int(round(((y1 + y2) / 2000.0) * screen_h))
                _click_coords_native(cx, cy)
                time.sleep(0.05)
            text_to_type = str(act_info.get("text") or "")
            _type_text_native(text_to_type)
            action_executed = True
            action_desc = f"Typed '{text_to_type[:20]}'"
            consecutive_scrolls = 0

        elif act_type == "scroll":
            amt = int(act_info.get("scroll_amount") or -450)
            _activate_presentation_window()
            # Click center of document canvas so browser viewport receives wheel scroll
            cx_mid = screen_w // 2
            cy_mid = int(screen_h * 0.55)
            _click_coords_native(cx_mid, cy_mid)
            time.sleep(0.04)
            _scroll_native(amt)
            consecutive_scrolls += 1
            action_executed = True
            action_desc = f"Scrolled page by {amt}"

            # Fallback: if consecutive scrolls occur, also tap PageDown/Down key to ensure viewport moves
            if consecutive_scrolls >= 2:
                time.sleep(0.04)
                _press_key_native("pagedown" if amt < 0 else "pageup")
                action_desc += " + pressed PageDown"

            # Clear recent clicks on scroll since viewport has shifted
            recent_clicks.clear()

        # 6. Visual Verification
        if action_executed:
            time.sleep(0.25)  # Snappy render wait
            img_after = _capture_screen_img()
            if img_after and _has_screen_changed(img, img_after, target_box=target_box_px):
                history.append(f"Cycle {cycles}: {action_desc} -> SUCCESS: Screen state changed as intended.")
                with _LOCK:
                    _TASK_STATE["triggers"] += 1
            else:
                history.append(f"Cycle {cycles}: {action_desc} -> NO CHANGE: Screen did not visibly move. Will adapt next action.")
                print(f"[ContinuousWork] [VERIFY_FAIL] {action_desc} produced no visual change. History updated.")

        # Minimal gap between cycles for ultra-fast reaction
        time.sleep(0.1)

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["waiting_for_user"] = False
        _TASK_STATE["status_msg"] = f"Finished ({cycles} cycles)"

    print(f"[ContinuousWork] [DONE] Autonomous Goal loop ended. Total cycles: {cycles}")


# -- Engine 2: High-Speed Verified Presentation Specialist ---------------------

def _find_next_slide_button(img: PIL.Image.Image) -> Optional[Tuple[int, int]]:
    """Locate Next/forward chevron button on viewer screen using vision."""
    from core import gemini
    from google.genai import types as gtypes

    orig_w, orig_h = img.size
    img_bytes = _compress_for_vision(img, max_dim=960)

    prompt = (
        "Find the 'Next slide' button, forward arrow button (> or ->), or next page button on this screen.\n"
        "Reply ONLY with its bounding box in normalized [0, 1000] format: [ymin, xmin, ymax, xmax].\n"
        "If not visible, reply ONLY: NOT_FOUND"
    )
    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=5000)
    if resp and getattr(resp, "text", ""):
        text = resp.text.strip()
        if "NOT_FOUND" not in text.upper():
            box_m = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', text)
            if box_m:
                y1, x1, y2, x2 = map(float, box_m.groups())
                cx = int(round(((x1 + x2) / 2000.0) * orig_w))
                cy = int(round(((y1 + y2) / 2000.0) * orig_h))
                return cx, cy
    return None


def _is_end_of_presentation(img: PIL.Image.Image) -> bool:
    """Fast check if the presentation has reached its conclusion or last page."""
    from core import gemini
    from google.genai import types as gtypes

    img_bytes = _compress_for_vision(img, max_dim=960)
    prompt = (
        "Is this the final slide or end of the document (e.g. 'Thank You', 'Questions?', 'Conclusion', last page)?\n"
        'Reply ONLY valid JSON: {"is_end": true or false}'
    )
    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=4000)
    if resp and getattr(resp, "text", ""):
        raw = resp.text.strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
        try:
            d = json.loads(raw)
            return bool(d.get("is_end", False))
        except Exception:
            pass
    return False


def _analyze_slide_linewise(img: PIL.Image.Image, slide_num: int) -> dict:
    """Analyze slide linewise and generate high-fidelity Hindi presentation speech."""
    from core import gemini
    from google.genai import types as gtypes

    img_bytes = _compress_for_vision(img, max_dim=960)

    prompt = (
        f"You are presenting Page/Slide {slide_num} of this document/presentation.\n"
        "Carefully read the visible text, title, and key bullet points on this screen.\n"
        "Explain the points accurately in 2 to 3 natural, polite spoken Hindi sentences.\n\n"
        "Return clean JSON:\n"
        "{\n"
        '  "slide_title": "Extracted Heading or Topic",\n'
        '  "speech": "Accurate linewise Hindi presentation speech",\n'
        '  "is_final": false\n'
        "}\n"
        "Emit ONLY valid JSON."
    )

    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=7000)

    fallback = {
        "slide_title": f"Page {slide_num}",
        "speech": f"Sir, page number {slide_num} screen par visible hai. Hum iske mukhya points ko cover kar rahe hain.",
        "is_final": False,
    }

    if not resp or not getattr(resp, "text", ""):
        return fallback

    raw = resp.text.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {
                "slide_title": str(data.get("slide_title") or f"Page {slide_num}").strip(),
                "speech": str(data.get("speech") or "").strip() or fallback["speech"],
                "is_final": bool(data.get("is_final", False)),
            }
    except Exception:
        pass

    return fallback


def _try_advance_method(
    method: str,
    img_before: PIL.Image.Image,
    screen_w: int,
    screen_h: int,
) -> Tuple[bool, Optional[PIL.Image.Image]]:
    """Try single slide advance method and verify outcome in 0.25s."""
    if _STOP_EVENT.is_set():
        return False, None

    try:
        if method == "pagedown":
            _activate_presentation_window()
            _press_key_native("pagedown")
        elif method == "right":
            _activate_presentation_window()
            _press_key_native("right")
        elif method == "space":
            _activate_presentation_window()
            _press_key_native("space")
        elif method == "scroll_down":
            _activate_presentation_window()
            _scroll_native(-450)
        elif method == "down":
            _activate_presentation_window()
            _press_key_native("down")
        elif method == "canvas_click":
            # Focus document center canvas then pagedown
            _click_coords_native(int(screen_w * 0.7), screen_h // 2)
            time.sleep(0.04)
            _press_key_native("pagedown")
        elif method == "next_button":
            btn = _find_next_slide_button(img_before)
            if btn:
                _click_coords_native(btn[0], btn[1])
            else:
                return False, None
        else:
            return False, None
    except Exception:
        return False, None

    time.sleep(0.25)  # Fast transition window
    img_after = _capture_screen_img()
    if img_after and _has_screen_changed(img_before, img_after):
        return True, img_after

    return False, img_after


def _advance_slide_fast(
    img_before: PIL.Image.Image,
    preferred_holder: dict,
    player,
) -> Tuple[bool, Optional[PIL.Image.Image]]:
    """Iterates candidate methods until slide advance is verified."""
    screen_w, screen_h = img_before.size
    candidates = ["pagedown", "right", "space", "scroll_down", "down", "canvas_click", "next_button"]

    pref = preferred_holder.get("method")
    if pref and pref in candidates:
        candidates.remove(pref)
        candidates.insert(0, pref)

    for m in candidates:
        if _STOP_EVENT.is_set():
            return False, None
        success, img_after = _try_advance_method(m, img_before, screen_w, screen_h)
        if success and img_after:
            preferred_holder["method"] = m
            return True, img_after

    return False, None


def _run_present_slides(
    interval: float,
    max_slides: int,
    player,
    speak_func,
):
    """High-speed autonomous slide presentation specialist."""
    global _TASK_STATE
    slide_num = 1
    preferred_holder = {"method": None}

    print(f"[ContinuousWork] [START] Fast Presentation Specialist started.")
    if player:
        player.write_log("[Presentation] Autonomous presentation starting...")

    time.sleep(0.2)

    while not _STOP_EVENT.is_set() and slide_num <= max_slides:
        with _LOCK:
            _TASK_STATE["cycles"] = slide_num
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Presenting Slide {slide_num}"

        img = _capture_screen_img()
        if not img or _STOP_EVENT.is_set():
            time.sleep(0.1)
            continue

        # Fast linewise vision extraction
        analysis = _analyze_slide_linewise(img, slide_num)
        title = analysis.get("slide_title", f"Page {slide_num}")
        speech = analysis.get("speech", "")
        is_final = analysis.get("is_final", False)

        log_line = f"[Presentation] Page {slide_num}: {title}"
        print(log_line)
        if player:
            player.write_log(log_line)
            try:
                player.show_content(f"PAGE {slide_num}: {title[:35]}", speech)
            except Exception:
                pass

        # Speak linewise explanation
        if speech and speak_func and not _STOP_EVENT.is_set():
            directive = f"[SYSTEM INSTRUCTION: PRESENT THE FOLLOWING SLIDE EXPLANATION IN POLITE HINDI]:\n{speech}"
            speak_func(directive)
            _wait_for_speech_to_finish(player, speech, max_wait=7.0)

        if _STOP_EVENT.is_set():
            break

        # Check if final slide reached
        if is_final:
            print("[ContinuousWork] [DONE] Final slide reached.")
            if player:
                player.write_log("[Presentation] Concluding final slide.")
            if speak_func:
                speak_func("Sir, presentation poori ho gayi hai. Agar koi sawal ho toh batayein.")
            break

        # Advance with verification
        print(f"[ContinuousWork] [NEXT] Advancing from Slide {slide_num}...")
        success, img_next = _advance_slide_fast(img, preferred_holder, player)

        if success:
            slide_num += 1
            with _LOCK:
                _TASK_STATE["triggers"] = slide_num
            time.sleep(0.1)
        else:
            # Check if presentation ended
            if _is_end_of_presentation(img):
                print("[ContinuousWork] [DONE] End of presentation confirmed.")
                if speak_func:
                    speak_func("Sir, presentation aakhri page tak complete ho gayi hai.")
                break
            else:
                # Ask user for help / focus window
                ans = _ask_user_and_wait(
                    "Sir, slide aage nahi badh pa rahi hai. Kripya presentation window par click kar dijiye ya agla page open karein.",
                    timeout=15.0,
                    player=player,
                    speak_func=speak_func,
                )
                time.sleep(0.3)

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["waiting_for_user"] = False
        _TASK_STATE["status_msg"] = f"Presentation finished at slide {slide_num}"

    print(f"[ContinuousWork] [DONE] Presentation engine finished.")


# -- Engine 3: Watch and Act (Conditional Button Clicker) -----------------------

def _run_watch_and_act(
    target: str,
    click_action: str,
    key: str,
    interval: float,
    max_cycles: int,
    player,
    speak_func,
):
    global _TASK_STATE
    from core import gemini
    from google.genai import types as gtypes

    cycles = 0
    triggers = 0
    last_trigger = 0.0

    print(f"[ContinuousWork] [START] Watch and act started for '{target}'")
    if player:
        player.write_log(f"[Watch & Act] Watching for '{target}' every {interval:.1f}s")

    while not _STOP_EVENT.is_set() and cycles < max_cycles:
        cycles += 1
        with _LOCK:
            _TASK_STATE["cycles"] = cycles
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Cycle {cycles}: Checking for '{target}'"

        img = _capture_screen_img()
        if img and (time.time() - last_trigger) > 2.0:
            screen_w, screen_h = img.size
            img_bytes = _compress_for_vision(img, max_dim=960)

            prompt = (
                f"Locate the UI element on screen matching: '{target}'.\n"
                f"If visible, reply ONLY normalized bounding box: [ymin, xmin, ymax, xmax].\n"
                f"If not visible, reply ONLY: NOT_FOUND"
            )
            part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=5000)

            if resp and getattr(resp, "text", "") and "NOT_FOUND" not in resp.text.upper():
                box_m = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', resp.text)
                if box_m and not _STOP_EVENT.is_set():
                    y1, x1, y2, x2 = map(float, box_m.groups())
                    cx = int(round(((x1 + x2) / 2000.0) * screen_w))
                    cy = int(round(((y1 + y2) / 2000.0) * screen_h))

                    triggers += 1
                    last_trigger = time.time()

                    log_msg = f"[ContinuousWork] Found '{target}' at ({cx}, {cy})! Performing {click_action}"
                    print(log_msg)
                    if player:
                        player.write_log(log_msg)

                    if click_action == "double_click":
                        _click_coords_native(cx, cy, double=True)
                    elif click_action == "right_click":
                        _click_coords_native(cx, cy, button="right")
                    elif click_action == "press_key" and key:
                        _click_coords_native(cx, cy)
                        time.sleep(0.04)
                        _press_key_native(key)
                    else:
                        _click_coords_native(cx, cy)

                    with _LOCK:
                        _TASK_STATE["triggers"] = triggers
                        _TASK_STATE["status_msg"] = f"Triggered {triggers} times"

        elapsed = 0.0
        while elapsed < interval and not _STOP_EVENT.is_set():
            time.sleep(0.15)
            elapsed += 0.15

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = f"Finished ({triggers} triggers)"


# -- Engine 4: Monitor Goal (Process Tracker) -----------------------------------

def _run_monitor_goal(
    goal_description: str,
    interval: float,
    max_cycles: int,
    player,
    speak_func,
):
    global _TASK_STATE
    from core import gemini
    from google.genai import types as gtypes

    cycles = 0
    print(f"[ContinuousWork] [START] Started goal monitor: '{goal_description}'")
    if player:
        player.write_log(f"[Monitor] Tracking: '{goal_description}'")

    while not _STOP_EVENT.is_set() and cycles < max_cycles:
        cycles += 1
        with _LOCK:
            _TASK_STATE["cycles"] = cycles
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Cycle {cycles}: Monitoring goal"

        img = _capture_screen_img()
        if img:
            img_bytes = _compress_for_vision(img, max_dim=960)
            prompt = (
                f"You are monitoring this screen for the goal: '{goal_description}'.\n"
                "Analyze screen and reply in JSON:\n"
                "{\n"
                '  "goal_achieved": true or false,\n'
                '  "progress_summary": "1-sentence summary of current screen progress",\n'
                '  "notification": "Short Hindi alert to speak to user if goal is achieved"\n'
                "}\n"
                "Emit ONLY valid JSON."
            )
            part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            resp = gemini.call([part, prompt], tier=gemini.FAST, timeout_ms=6000)
            if resp and getattr(resp, "text", ""):
                raw = resp.text.strip()
                raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
                raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
                try:
                    data = json.loads(raw)
                    achieved = bool(data.get("goal_achieved", False))
                    progress = data.get("progress_summary", "")
                    notify = data.get("notification", "")
                    if progress and player:
                        player.write_log(f"[Monitor] {progress}")
                    if achieved:
                        print(f"[ContinuousWork] [ACHIEVED] Goal achieved: {goal_description}")
                        if speak_func and notify:
                            speak_func(notify)
                        elif speak_func:
                            speak_func(f"Sir, {goal_description} complete ho gaya hai.")
                        break
                except Exception:
                    pass

        elapsed = 0.0
        while elapsed < interval and not _STOP_EVENT.is_set():
            time.sleep(0.15)
            elapsed += 0.15

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = "Monitor finished"


# -- Action Entry Point --------------------------------------------------------

def continuous_work(
    parameters: dict = None,
    response=None,
    player=None,
    speak=None,
    session_memory=None,
) -> str:
    global _WORKER_THREAD, _TASK_STATE

    params = parameters or {}
    raw_action = params.get("action", "").lower().strip()
    target = params.get("target", "").strip()
    click_action = params.get("click_action", "click").lower().strip()
    key = params.get("key", "").strip()
    goal_desc = params.get("goal_description", "").strip()
    interval = float(params.get("interval_seconds") or 1.5)
    interval = max(0.5, min(10.0, interval))
    max_cycles = int(params.get("max_cycles") or 100)

    # Normalize action alias
    action = "status"
    if any(w in raw_action for w in ("stop", "cancel", "halt", "ruko", "band")):
        action = "stop"
    elif any(w in raw_action for w in ("present_slides", "present_presentation", "present_deck", "presentation")):
        action = "present_slides"
    elif any(w in raw_action for w in ("watch_and_act", "continuous_watch", "periodic_watch")):
        action = "watch_and_act"
    elif any(w in raw_action for w in ("monitor_goal", "continuous_monitor")):
        action = "monitor_goal"
    elif any(w in raw_action for w in ("autonomous_goal", "goal", "auto_goal", "execute_goal", "task", "workflow")):
        action = "autonomous_goal"
    elif raw_action in ("status", "info"):
        action = "status"
    elif goal_desc:
        action = "autonomous_goal"

    # 1. Stop
    if action == "stop":
        return stop_continuous_work()

    # 2. Status
    if action == "status":
        st = get_status()
        if st["active"]:
            waiting = f" (Waiting for user: {st['last_question']})" if st.get("waiting_for_user") else ""
            return (
                f"Continuous work is ACTIVE (mode: {st['mode']}). "
                f"Cycles completed: {st['cycles']}, triggers: {st['triggers']}. "
                f"Status: {st['status_msg']}{waiting}."
            )
        return "No continuous work is currently running."

    # 3. Start new task -- Halts any previous task cleanly
    with _LOCK:
        if _TASK_STATE["active"]:
            _STOP_EVENT.set()
            _USER_FEEDBACK_EVENT.set()
        _STOP_EVENT.clear()
        _USER_FEEDBACK_EVENT.clear()
        _TASK_STATE["active"] = True
        _TASK_STATE["mode"] = action
        _TASK_STATE["target"] = target or goal_desc or "Autonomous Goal"
        _TASK_STATE["goal"] = goal_desc or target or "Presentation"
        _TASK_STATE["cycles"] = 0
        _TASK_STATE["triggers"] = 0
        _TASK_STATE["start_time"] = time.time()
        _TASK_STATE["waiting_for_user"] = False
        _TASK_STATE["last_question"] = None
        _TASK_STATE["status_msg"] = f"Initializing {action}..."

    # Launch worker thread
    if action == "present_slides":
        _WORKER_THREAD = threading.Thread(
            target=_run_present_slides,
            args=(interval, max_slides := max_cycles, player, speak),
            daemon=True,
            name="jarvis-present-slides",
        )
        _WORKER_THREAD.start()
        msg = "Autonomous presentation engine started. Explaining each slide in Hindi with verified auto-advancing."
        if player:
            player.write_log("[ContinuousWork] Started presentation presenter")
        return msg

    elif action == "autonomous_goal":
        goal_text = goal_desc or target or "Execute continuous desktop workflow"
        _WORKER_THREAD = threading.Thread(
            target=_run_autonomous_goal,
            args=(goal_text, interval, max_cycles, player, speak, session_memory),
            daemon=True,
            name="jarvis-auto-goal",
        )
        _WORKER_THREAD.start()
        msg = f"Autonomous Goal Engine started for: '{goal_text}'. Perceiving screen, executing steps, verifying, and persisting until completion."
        if player:
            player.write_log(f"[ContinuousWork] Started autonomous goal: {goal_text}")
        return msg

    elif action == "watch_and_act":
        if not target:
            target = "Next or Continue button"
        _WORKER_THREAD = threading.Thread(
            target=_run_watch_and_act,
            args=(target, click_action, key, interval, max_cycles, player, speak),
            daemon=True,
            name="jarvis-watch-and-act",
        )
        _WORKER_THREAD.start()
        msg = f"Continuous watcher started for '{target}' every {interval:.1f}s."
        if player:
            player.write_log(f"[ContinuousWork] Watching for '{target}'")
        return msg

    elif action == "monitor_goal":
        if not goal_desc:
            goal_desc = "active desktop process"
        _WORKER_THREAD = threading.Thread(
            target=_run_monitor_goal,
            args=(goal_desc, interval, max_cycles, player, speak),
            daemon=True,
            name="jarvis-monitor-goal",
        )
        _WORKER_THREAD.start()
        msg = f"Monitoring screen for '{goal_desc}'."
        if player:
            player.write_log(f"[ContinuousWork] Monitoring: '{goal_desc}'")
        return msg

    return f"Unknown continuous_work action '{action}'."


# -- Action Tool Declaration for Discovery -------------------------------------

TOOL = {
    "name": "continuous_work",
    "description": (
        "Starts, monitors, or stops autonomous continuous screen workflows. "
        "Use this tool whenever the user asks for ongoing, continuous, or multi-step goal execution: "
        "(1) 'autonomous_goal': Generalized autonomous perception-action loop for ANY multi-step desktop task "
        "(e.g. 'ye kaam pura karo', 'is process ko step by step continue karo', 'document ko check karke aage badho', 'screen dekhke task complete karo'). "
        "Perceives screen, plans next action, verifies outcome, and asks the user for clarification if blocked. "
        "(2) 'present_slides': Autonomously present a PowerPoint/PDF/deck slide-by-slide linewise in Hindi, "
        "verifying each page change and advancing until the conclusion. "
        "(3) 'watch_and_act': Continuously watch screen for a specific button or element and click/press key whenever it appears "
        "(e.g. 'jab jab Skip button dikhe click kar dena', 'jab ye popup aaye submit kar dena'). "
        "(4) 'monitor_goal': Continuously track screen progress for an ongoing download or long task. "
        "(5) 'stop': Cancel and stop any active continuous work immediately (e.g. 'ruko', 'stop', 'band karo')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'autonomous_goal' | 'present_slides' | 'watch_and_act' | 'monitor_goal' | 'status' | 'stop'"
            },
            "goal_description": {
                "type": "STRING",
                "description": "The user's high-level goal, workflow intent, or presentation topic to autonomously execute"
            },
            "target": {
                "type": "STRING",
                "description": "The button, element, or visual cue to watch for in 'watch_and_act'"
            },
            "click_action": {
                "type": "STRING",
                "description": "'click' (default) | 'double_click' | 'right_click' | 'press_key'"
            },
            "key": {
                "type": "STRING",
                "description": "Key name if click_action is press_key (e.g. 'enter', 'space', 'right')"
            },
            "interval_seconds": {
                "type": "NUMBER",
                "description": "Seconds between perception cycles (default: 1.5, range: 0.5 to 10.0)"
            },
            "max_cycles": {
                "type": "INTEGER",
                "description": "Maximum number of check cycles or slides before auto-stopping (default: 100)"
            }
        },
        "required": ["action"]
    },
    "handler": continuous_work,
}
