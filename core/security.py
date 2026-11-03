"""
core/security.py
High-Security Authorization Gate for JARVIS.

Protects against any unauthorized deletion, removal, wiping, or trashing of files,
folders, long-term memories, cache, or system resources.

Enforces the 3-word passphrase: "tulip paris cake"
Any delete action must be explicitly authorized with this passphrase.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

# Required High-Security 3-word passphrase
SECURITY_PASSPHRASE = "tulip paris cake"

# Normalized token set for flexible matching
_PASSPHRASE_WORDS = set(SECURITY_PASSPHRASE.split())

_LOCK = threading.Lock()
_LAST_AUTH_TIME = 0.0
# Grace window in seconds after user speaks/enters valid password (for immediate multi-turn operations)
_AUTH_GRACE_WINDOW = 30.0


def normalize_text(text: str) -> str:
    """Normalize input text: lowercased, stripped, punctuation to spaces, single-spaced."""
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def verify_security_password(attempt: Optional[str]) -> bool:
    """
    Check if the given attempt contains or matches the required 3 words:
    'tulip paris cake'.
    Returns True if authorized, False otherwise.
    """
    if not attempt:
        return False
    norm = normalize_text(attempt)
    if not norm:
        return False

    # Direct substring match
    if SECURITY_PASSPHRASE in norm:
        return True

    # Word-set match (all 3 words present)
    words = set(norm.split())
    if _PASSPHRASE_WORDS.issubset(words):
        return True

    return False


def authorize_session() -> None:
    """Temporarily authorize the current session for 30 seconds after password verified."""
    global _LAST_AUTH_TIME
    with _LOCK:
        _LAST_AUTH_TIME = time.time()


def is_session_authorized() -> bool:
    """Check if the session has a recently verified password within the grace window."""
    with _LOCK:
        return (time.time() - _LAST_AUTH_TIME) < _AUTH_GRACE_WINDOW


def is_delete_operation(tool_name: str, args: dict) -> bool:
    """
    Introspect tool name and arguments to determine if an action attempts deletion.
    """
    if not tool_name:
        return False

    args = args or {}
    t_name = tool_name.lower().strip()
    action = str(args.get("action") or "").lower().strip()

    # 1. file_controller: delete, remove, trash
    if t_name == "file_controller":
        if action in ("delete", "remove", "trash", "unlink", "del"):
            return True

    # 2. storage_control: clearing cache, memory, or wiping
    if t_name == "storage_control":
        if action in (
            "clear_cache", "clean_cache", "clear_temp",
            "clear_memory", "reset_memory", "forget_all",
            "clean_all", "clear_all", "wipe"
        ):
            return True

    # 3. computer_control: destructive keys or commands
    if t_name == "computer_control":
        key = str(args.get("key") or "").lower().strip()
        cmd = str(args.get("command") or "").lower().strip()
        desc = str(args.get("description") or "").lower().strip()

        if action in ("press", "key") and key in ("delete", "del", "backspace"):
            return True
        if any(d in desc for d in ("delete", "remove", "trash", "recycle", "wipe", "del ")):
            return True
        if any(c in cmd for c in ("rm ", "del ", "remove-item", "rmdir", "unlink", "format ")):
            return True

    # 4. code_helper / dev_agent running shell deletion
    if t_name in ("code_helper", "dev_agent"):
        desc = str(args.get("description") or "").lower()
        code = str(args.get("code") or "").lower()
        if any(w in desc for w in ("delete file", "delete folder", "remove file", "unlink")):
            return True
        if any(w in code for w in ("os.remove", "shutil.rmtree", "unlink", "remove-item")):
            return True

    # 5. Generic check on action name
    if action in ("delete", "remove", "wipe", "purge", "trash"):
        return True

    return False


def get_security_prompt_instruction() -> str:
    """Instruction returned to model when a deletion action is blocked."""
    return (
        "SECURITY AUTHORIZATION REQUIRED: Deletion is locked by High Security. "
        "Do NOT perform any deletion directly. You must ask the user out loud in polite Hindi: "
        "'Ye action high-security protected hai. Kripya authorization password batayein.' "
        "Only when the user speaks the exact password 'tulip paris cake', include password='tulip paris cake' "
        "to execute the deletion."
    )
