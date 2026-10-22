from __future__ import annotations

import json
from typing import Optional

from memory.storage_manager import (
    get_storage_stats,
    clear_browser_cache,
    clear_temp_files,
    clear_memory,
    clear_all_storage,
    format_bytes,
)


def storage_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "status").lower().strip()
    keep_id = params.get("keep_identity", False)

    if action in ("status", "info", "get", "stats", "display"):
        stats = get_storage_stats()
        result = (
            f"Jarvis Storage Status:\n"
            f"• Total Storage Used: {stats['total_formatted']}\n"
            f"• Long-Term Memory: {stats['memory_formatted']} ({stats['facts_count']} facts stored)\n"
            f"• Browser Automation Cache: {stats['browser_cache_formatted']}\n"
            f"• Temporary & Scratch Files: {stats['temp_formatted']}"
        )
        if player:
            player.write_log(f"[storage] Total: {stats['total_formatted']}")
        return result

    if action in ("clear_cache", "clean_cache", "clear_temp"):
        freed_cache = clear_browser_cache()
        freed_temp = clear_temp_files()
        total_freed = freed_cache + freed_temp
        stats = get_storage_stats()
        result = (
            f"Cache and temporary files cleared successfully.\n"
            f"• Space freed: {format_bytes(total_freed)}\n"
            f"• Remaining storage: {stats['total_formatted']}"
        )
        if player:
            player.write_log(f"[storage] Freed {format_bytes(total_freed)}")
        return result

    if action in ("clear_memory", "reset_memory", "forget_all"):
        freed_mem = clear_memory(keep_identity=keep_id)
        stats = get_storage_stats()
        result = (
            f"Long-term memory has been cleared successfully.\n"
            f"• Memory size: {stats['memory_formatted']}\n"
            f"• Remaining facts: {stats['facts_count']}"
        )
        if player:
            player.write_log("[storage] Memory cleared")
        return result

    if action in ("clean_all", "clear_all", "wipe"):
        summary = clear_all_storage()
        stats = get_storage_stats()
        result = (
            f"All Jarvis storage and memory cleared.\n"
            f"• Total space freed: {summary['freed_formatted']}\n"
            f"• Browser cache freed: {summary['freed_cache']}\n"
            f"• Remaining total storage: {stats['total_formatted']}"
        )
        if player:
            player.write_log(f"[storage] Wiped {summary['freed_formatted']}")
        return result

    return f"Unknown storage action: '{action}'. Use status, clear_cache, clear_memory, or clean_all."


TOOL = {
    "name": "storage_control",
    "description": (
        "Inspects or clears Jarvis's storage and memory to free up disk space. "
        "Use action='status' to display how much storage is being used by memory, browser profiles, and cache. "
        "Use action='clear_cache' to delete browser profiles and temporary files. "
        "Use action='clear_memory' to wipe stored facts from long_term.json memory. "
        "Use action='clean_all' to wipe both cache and memory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | clear_cache | clear_memory | clean_all (default: status)"
            },
            "keep_identity": {
                "type": "BOOLEAN",
                "description": "When clearing memory, set to true to keep user name and language preferences. Default is false."
            }
        }
    },
    "handler": storage_control,
}
