"""
actions/continuous_work.py
Continuous Autonomous Work Engine for JARVIS.

Enables real-time, periodic screen perception (every 3 to 5 seconds) to execute
continuous, repetitive, and autonomous multi-step tasks without stopping after a single turn.

Capabilities:
1. 'watch_and_act': Continuously watch the screen for a specific button or element
   (e.g. "Next", "Skip Ad", "Submit", "Download") and automatically click or press a key
   whenever it appears.
2. 'present_slides': Autonomous presentation presenter. Reads and analyzes the presentation
   slide on screen, delivers an engaging speech explaining it in polite Hindi, automatically
   detects when the slide speech finishes, and advances to the next slide (Right/PageDown),
   continuing until the presentation finishes.
3. 'monitor_goal': Continuously tracks screen progress towards a goal (e.g. download finishing).
4. 'status': Reports the current active continuous task and cycle count.
5. 'stop': Cancels and halts any active continuous work immediately.
"""

from __future__ import annotations

import io
import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

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


# -- Global Task State ----------------------------------------------------------

_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()
_WORKER_THREAD: Optional[threading.Thread] = None

_TASK_STATE = {
    "active": False,
    "mode": None,
    "target": None,
    "cycles": 0,
    "triggers": 0,
    "start_time": 0.0,
    "last_check": 0.0,
    "status_msg": "Idle",
}


def is_active() -> bool:
    with _LOCK:
        return _TASK_STATE["active"]


def get_status() -> dict:
    with _LOCK:
        return dict(_TASK_STATE)


def stop_continuous_work() -> str:
    global _WORKER_THREAD
    with _LOCK:
        if not _TASK_STATE["active"]:
            return "No continuous task is currently active."
        _STOP_EVENT.set()
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = "Stopped by user"
    
    print("[ContinuousWork] [STOP] Stop requested.")
    return "Continuous work stopped successfully."


# -- Screen Capture & Perception Helpers ----------------------------------------

def _capture_screen_img() -> Optional[PIL.Image.Image]:
    """Capture current screen with robust fallbacks."""
    if _MSS:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                return PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            pass

    if _PIL:
        try:
            return PIL.ImageGrab.grab(all_screens=True).convert("RGB")
        except Exception:
            pass

    if _PYAUTOGUI:
        try:
            return pyautogui.screenshot().convert("RGB")
        except Exception:
            pass

    return None


def _compress_for_vision(img: PIL.Image.Image, max_dim: int = 1280) -> bytes:
    """Resize image to max dimensions and compress to JPEG bytes for low latency."""
    im = img.copy()
    im.thumbnail((max_dim, max_dim), PIL.Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def _image_hash(img: PIL.Image.Image) -> str:
    """Fast perceptual thumbnail hash to compare consecutive screen states."""
    try:
        small = img.resize((16, 16), PIL.Image.Resampling.BILINEAR).convert("L")
        pixels = list(small.getdata())
        avg = sum(pixels) / float(len(pixels))
        return "".join("1" if p > avg else "0" for p in pixels)
    except Exception:
        return ""


def _hash_distance(h1: str, h2: str) -> int:
    """Hamming distance between two image hashes."""
    if not h1 or not h2 or len(h1) != len(h2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


# -- Vision Grounding for Buttons / Elements -----------------------------------

def _find_element_box(target_desc: str, img: PIL.Image.Image) -> Optional[tuple[int, int]]:
    """Use Gemini Vision to locate the target element/button on screen."""
    from core import gemini
    from google.genai import types as gtypes

    orig_w, orig_h = img.size
    img_bytes = _compress_for_vision(img)

    prompt = (
        f"Locate the UI element on this screen matching: '{target_desc}'.\n"
        f"If the element or button is visible, reply ONLY with its bounding box in normalized [0, 1000] format: [ymin, xmin, ymax, xmax].\n"
        f"Example: [420, 310, 480, 550]\n"
        f"If the element is definitely NOT visible anywhere on screen, reply ONLY: NOT_FOUND"
    )

    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = gemini.call([part, prompt], tier=gemini.SMART, timeout_ms=10000)

    if not resp or not getattr(resp, "text", ""):
        return None

    text = resp.text.strip()
    if "NOT_FOUND" in text.upper():
        return None

    box_m = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', text)
    if box_m:
        y1, x1, y2, x2 = map(float, box_m.groups())
        cx = int(round(((x1 + x2) / 2000.0) * orig_w))
        cy = int(round(((y1 + y2) / 2000.0) * orig_h))
        return cx, cy

    return None


# -- Slide Presentation Vision Analysis ----------------------------------------

def _analyze_slide(img: PIL.Image.Image, slide_num: int) -> dict:
    """Analyze current presentation slide and generate presenter speech in Hindi."""
    from core import gemini
    from google.genai import types as gtypes

    img_bytes = _compress_for_vision(img)

    prompt = (
        f"You are an expert keynote speaker presenting this slide (Slide {slide_num}) to an audience.\n"
        "Examine the slide currently displayed on the computer screen.\n"
        "Produce a clean JSON response with the following keys:\n"
        "{\n"
        '  "is_slide": true,\n'
        '  "slide_title": "Short title or topic of this slide",\n'
        '  "speech": "An engaging, professional, natural spoken presentation in polite Hindi / Hinglish explaining this slide. As the presenter, explain the main heading, key points, charts, or diagrams clearly and concisely in 2 to 4 sentences. Speak naturally to the audience.",\n'
        '  "is_final": false\n'
        "}\n"
        "Note: set 'is_final' to true if this is the concluding or final slide (e.g. contains Thank You, Questions?, Q&A, Conclusion, The End, or final credits).\n"
        "Emit ONLY valid JSON. No markdown fences, no extra commentary."
    )

    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = gemini.call([part, prompt], tier=gemini.SMART, timeout_ms=15000)

    fallback = {
        "is_slide": True,
        "slide_title": f"Slide {slide_num}",
        "speech": f"Sir, slide number {slide_num} screen par visible hai. Hum iske mukhya points ko review kar rahe hain.",
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
                "is_slide": bool(data.get("is_slide", True)),
                "slide_title": str(data.get("slide_title") or f"Slide {slide_num}").strip(),
                "speech": str(data.get("speech") or "").strip(),
                "is_final": bool(data.get("is_final", False)),
            }
    except Exception as e:
        print(f"[ContinuousWork] JSON parse error: {e}")

    return fallback


# -- Worker 1: Watch and Act (Conditional Button Clicker) -----------------------

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
    cycles = 0
    triggers = 0
    last_trigger_time = 0.0

    print(f"[ContinuousWork] [START] Started watch_and_act for '{target}' every {interval:.1f}s")
    if player:
        player.write_log(f"[ContinuousWork] Watching screen for '{target}' every {interval:.1f}s")

    while not _STOP_EVENT.is_set() and cycles < max_cycles:
        cycles += 1
        with _LOCK:
            _TASK_STATE["cycles"] = cycles
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Cycle {cycles}: Checking for '{target}'"

        img = _capture_screen_img()
        if img:
            now = time.time()
            # Avoid duplicate click within 3 seconds of last trigger
            if now - last_trigger_time > 3.0:
                coords = _find_element_box(target, img)
                if coords and not _STOP_EVENT.is_set():
                    cx, cy = coords
                    triggers += 1
                    last_trigger_time = now

                    log_msg = f"[ContinuousWork] [TARGET] Found '{target}' at ({cx}, {cy})! Performing {click_action}"
                    print(log_msg)
                    if player:
                        player.write_log(log_msg)

                    if _PYAUTOGUI:
                        if click_action == "double_click":
                            pyautogui.doubleClick(cx, cy)
                        elif click_action == "right_click":
                            pyautogui.rightClick(cx, cy)
                        elif click_action == "press_key" and key:
                            pyautogui.click(cx, cy)
                            time.sleep(0.1)
                            pyautogui.press(key)
                        else:
                            pyautogui.click(cx, cy)

                    with _LOCK:
                        _TASK_STATE["triggers"] = triggers
                        _TASK_STATE["status_msg"] = f"Triggered {triggers} times. Last at ({cx}, {cy})"

        # Sleep interval in small chunks to remain responsive to stop event
        elapsed = 0.0
        while elapsed < interval and not _STOP_EVENT.is_set():
            time.sleep(0.2)
            elapsed += 0.2

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = f"Finished ({triggers} triggers in {cycles} cycles)"

    print(f"[ContinuousWork] [DONE] watch_and_act finished. Total triggers: {triggers}")
    if player:
        player.write_log(f"[ContinuousWork] Finished watching '{target}'. Total triggers: {triggers}")


# -- Worker 2: Autonomous Slide Presenter ---------------------------------------

def _run_present_slides(
    interval: float,
    max_slides: int,
    player,
    speak_func,
):
    global _TASK_STATE
    slide_num = 1
    prev_hash = ""
    identical_count = 0

    print(f"[ContinuousWork] [START] Started autonomous slide presentation engine")
    if player:
        player.write_log(f"[Presentation] Starting autonomous slide presentation...")

    if speak_func:
        speak_func("Sir, presentation start kar raha hu. Main slide by slide explain karke automatically aage badhta rahunga.")

    # Give speech a moment to initiate and user time to ensure presentation is visible
    time.sleep(3.5)

    while not _STOP_EVENT.is_set() and slide_num <= max_slides:
        with _LOCK:
            _TASK_STATE["cycles"] = slide_num
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Presenting Slide {slide_num}"

        img = _capture_screen_img()
        if not img or _STOP_EVENT.is_set():
            time.sleep(1.0)
            continue

        curr_hash = _image_hash(img)
        # Check if screen hasn't changed despite moving next (end of presentation reached)
        if slide_num > 1 and prev_hash and _hash_distance(prev_hash, curr_hash) < 4:
            identical_count += 1
            if identical_count >= 2:
                print(f"[ContinuousWork] [DONE] Presentation reached final slide (no more screen changes).")
                if player:
                    player.write_log("[Presentation] Reached the end of slides.")
                if speak_func:
                    speak_func("Sir, slides poori ho gayi hain. Presentation complete ho chuka hai.")
                break
        else:
            identical_count = 0

        prev_hash = curr_hash

        # Analyze slide with Gemini Vision
        analysis = _analyze_slide(img, slide_num)
        title = analysis.get("slide_title", f"Slide {slide_num}")
        speech = analysis.get("speech", "")
        is_final = analysis.get("is_final", False)

        log_line = f"[Presentation] Slide {slide_num}: {title}"
        print(log_line)
        if player:
            player.write_log(log_line)
            try:
                player.show_content(f"SLIDE {slide_num}: {title[:35]}", speech)
            except Exception:
                pass

        # Deliver spoken presentation for this slide
        if speech and speak_func and not _STOP_EVENT.is_set():
            speak_func(speech)

            # Calculate expected speaking duration based on word count
            word_count = len(speech.split())
            expected_sec = max(4.0, (word_count / 2.2) + 2.0)

            # Wait while player is speaking or until expected duration has elapsed
            t0 = time.time()
            time.sleep(1.5)  # initial grace for audio to begin
            while (time.time() - t0) < (expected_sec + 3.0) and not _STOP_EVENT.is_set():
                is_spk = False
                if player and hasattr(player, "is_speaking"):
                    is_spk = player.is_speaking()
                elif player and hasattr(player, "_win") and hasattr(player._win, "hud"):
                    is_spk = getattr(player._win.hud, "speaking", False)

                # If speech finished and minimal time elapsed, break
                if not is_spk and (time.time() - t0) >= expected_sec:
                    break
                time.sleep(0.3)

        # Brief pause for audience absorption
        elapsed = 0.0
        while elapsed < interval and not _STOP_EVENT.is_set():
            time.sleep(0.3)
            elapsed += 0.3

        if _STOP_EVENT.is_set():
            break

        # Check if this slide is the final conclusion slide
        if is_final:
            print("[ContinuousWork] [DONE] Final slide detected via vision analysis.")
            if player:
                player.write_log("[Presentation] Concluding final slide.")
            if speak_func:
                speak_func("Sir, presentation poori ho gayi hai. Agar koi questions ho toh batayein.")
            break

        # Automatically advance to next slide!
        print(f"[ContinuousWork] [NEXT] Auto-advancing from Slide {slide_num} to Slide {slide_num + 1}")
        if _PYAUTOGUI and not _STOP_EVENT.is_set():
            pyautogui.press("right")

        slide_num += 1
        with _LOCK:
            _TASK_STATE["triggers"] = slide_num

        # Transition wait for slide animation
        time.sleep(2.0)

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = f"Presentation finished at slide {slide_num}"

    print(f"[ContinuousWork] [DONE] Presentation engine finished.")
    if player:
        player.write_log(f"[Presentation] Autonomous presentation finished.")


# -- Worker 3: Goal Monitor ----------------------------------------------------

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
        player.write_log(f"[ContinuousWork] Monitoring goal: '{goal_description}'")

    while not _STOP_EVENT.is_set() and cycles < max_cycles:
        cycles += 1
        with _LOCK:
            _TASK_STATE["cycles"] = cycles
            _TASK_STATE["last_check"] = time.time()
            _TASK_STATE["status_msg"] = f"Cycle {cycles}: Monitoring goal"

        img = _capture_screen_img()
        if img:
            img_bytes = _compress_for_vision(img)
            prompt = (
                f"You are monitoring this screen for the goal: '{goal_description}'.\n"
                "Analyze the screen and answer in JSON:\n"
                "{\n"
                '  "goal_achieved": true or false,\n'
                '  "progress_summary": "Brief 1-sentence description of current screen progress",\n'
                '  "notification": "Short Hindi alert to speak to user if goal is achieved or critical event happened"\n'
                "}\n"
                "Emit ONLY valid JSON."
            )
            part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            resp = gemini.call([part, prompt], tier=gemini.SMART, timeout_ms=10000)
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
                        if player:
                            player.write_log(f"[ContinuousWork] Goal achieved: {goal_description}")
                        if speak_func and notify:
                            speak_func(notify)
                        elif speak_func:
                            speak_func(f"Sir, {goal_description} complete ho gaya hai.")
                        break
                except Exception:
                    pass

        elapsed = 0.0
        while elapsed < interval and not _STOP_EVENT.is_set():
            time.sleep(0.3)
            elapsed += 0.3

    with _LOCK:
        _TASK_STATE["active"] = False
        _TASK_STATE["status_msg"] = "Monitor finished"


# -- Action Entry Point ---------------------------------------------------------

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
    interval = float(params.get("interval_seconds") or 4.0)
    interval = max(2.0, min(15.0, interval))
    max_cycles = int(params.get("max_cycles") or (100 if "present" in raw_action else 60))

    # Normalize action alias
    action = "status"
    if any(w in raw_action for w in ("stop", "cancel", "halt", "ruko", "band")):
        action = "stop"
    elif any(w in raw_action for w in ("present", "slide", "ppt", "powerpoint")):
        action = "present_slides"
    elif any(w in raw_action for w in ("watch", "click", "daba", "button", "trigger", "act")):
        action = "watch_and_act"
    elif any(w in raw_action for w in ("monitor", "track", "check", "goal")):
        action = "monitor_goal"
    elif raw_action in ("status", "info"):
        action = "status"
    elif target:
        action = "watch_and_act"
    elif goal_desc:
        action = "monitor_goal"

    # 1. Stop
    if action == "stop":
        return stop_continuous_work()

    # 2. Status
    if action == "status":
        st = get_status()
        if st["active"]:
            return (
                f"Continuous work is ACTIVE (mode: {st['mode']}). "
                f"Cycles completed: {st['cycles']}, triggers: {st['triggers']}. "
                f"Status: {st['status_msg']}."
            )
        return "No continuous work is currently running."

    # 3. Start new task -- Stop previous task if running
    with _LOCK:
        if _TASK_STATE["active"]:
            _STOP_EVENT.set()
        _STOP_EVENT.clear()
        _TASK_STATE["active"] = True
        _TASK_STATE["mode"] = action
        _TASK_STATE["target"] = target or goal_desc or "Presentation"
        _TASK_STATE["cycles"] = 0
        _TASK_STATE["triggers"] = 0
        _TASK_STATE["start_time"] = time.time()
        _TASK_STATE["status_msg"] = f"Initializing {action}..."

    if action == "present_slides":
        _WORKER_THREAD = threading.Thread(
            target=_run_present_slides,
            args=(interval, max_cycles, player, speak),
            daemon=True,
            name="jarvis-present-slides",
        )
        _WORKER_THREAD.start()
        msg = (
            f"Autonomous presentation engine started. I will analyze each slide, "
            f"explain it in Hindi, and automatically advance to the next slide every {interval:.1f}s until finished."
        )
        if player:
            player.write_log(f"[ContinuousWork] Started presentation presenter")
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
        msg = (
            f"Continuous screen watcher started for '{target}'. "
            f"Checking screen every {interval:.1f} seconds to perform {click_action} whenever it appears."
        )
        if player:
            player.write_log(f"[ContinuousWork] Watching for '{target}' ({interval:.1f}s interval)")
        return msg

    elif action == "monitor_goal":
        if not goal_desc:
            goal_desc = "active screen task"
        _WORKER_THREAD = threading.Thread(
            target=_run_monitor_goal,
            args=(goal_desc, interval, max_cycles, player, speak),
            daemon=True,
            name="jarvis-monitor-goal",
        )
        _WORKER_THREAD.start()
        msg = (
            f"Continuous goal monitoring started for '{goal_desc}'. "
            f"Checking screen progress every {interval:.1f} seconds."
        )
        if player:
            player.write_log(f"[ContinuousWork] Monitoring goal: '{goal_desc}'")
        return msg

    return f"Unknown continuous_work action '{action}'."


# -- Action Tool Declaration for Discovery -------------------------------------

TOOL = {
    "name": "continuous_work",
    "description": (
        "Starts, monitors, or stops autonomous continuous screen workflows. "
        "Use this tool whenever the user asks for ongoing, continuous, or repetitive tasks such as: "
        "(1) 'watch_and_act': continuously watch the screen every 3-5 seconds for a specific button or element and click/press it whenever it appears (e.g. 'jab jab ye button aaye daba dena', 'jab Skip button dikhe click kar dena'); "
        "(2) 'present_slides': autonomously present a PowerPoint/PDF/Google Slides presentation slide-by-slide, speaking and explaining each slide in Hindi, then automatically pressing next to continue until the presentation ends (e.g. 'mere pass ppt hai use pura present karo', 'slide by slide presentation do'); "
        "(3) 'monitor_goal': continuously observe screen progress for an ongoing task, download, or process; "
        "(4) 'stop': cancel and stop any active continuous work immediately (e.g. 'ruko', 'stop presentation', 'monitoring band karo')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'watch_and_act' | 'present_slides' | 'monitor_goal' | 'status' | 'stop'"
            },
            "target": {
                "type": "STRING",
                "description": "The button, element, or visual cue to watch for in 'watch_and_act' (e.g. 'Next button', 'Skip button', 'Submit button', 'Confirm popup')"
            },
            "click_action": {
                "type": "STRING",
                "description": "'click' (default) | 'double_click' | 'right_click' | 'press_key'"
            },
            "key": {
                "type": "STRING",
                "description": "Key name if click_action is press_key (e.g. 'enter', 'space', 'right')"
            },
            "goal_description": {
                "type": "STRING",
                "description": "Description of the ongoing task or presentation topic to monitor"
            },
            "interval_seconds": {
                "type": "NUMBER",
                "description": "Seconds between periodic screen checks (default: 4.0, recommended 3.0 to 5.0)"
            },
            "max_cycles": {
                "type": "INTEGER",
                "description": "Maximum number of check cycles or slides before auto-stopping (default: 60 for watch, 100 for slides)"
            }
        },
        "required": ["action"]
    },
    "handler": continuous_work,
}
