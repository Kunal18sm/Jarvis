import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any

from memory.memory_manager import (
    MEMORY_PATH,
    BASE_DIR,
    load_memory,
    save_memory,
    _empty_memory,
)


def _get_path_size(p: Path) -> int:
    try:
        if not p.exists():
            return 0
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except Exception:
        return 0


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


def get_storage_stats() -> Dict[str, Any]:
    """Calculates storage used by Jarvis memory, browser profiles/cache, and temporary files."""
    home = Path.home()

    # 1. Long term memory
    mem_size = _get_path_size(MEMORY_PATH)

    # Count stored facts
    mem_data = load_memory()
    total_facts = 0
    for cat, items in mem_data.items():
        if isinstance(items, dict):
            total_facts += len(items)
        elif isinstance(items, list):
            total_facts += len(items)

    # 2. Browser profiles & cache
    browser_profiles_dir = home / ".jarvis_profiles"
    browser_cache_size = _get_path_size(browser_profiles_dir)

    # 3. Temp files, scratch, screenshots
    scratch_dir = BASE_DIR / "scratch"
    scratch_size = _get_path_size(scratch_dir)

    screenshot_path = home / "Desktop" / "jarvis_screenshot.png"
    screenshot_size = _get_path_size(screenshot_path)

    temp_dir = Path(tempfile.gettempdir())
    temp_jarvis_size = 0
    try:
        for p in temp_dir.glob("jarvis_*"):
            temp_jarvis_size += _get_path_size(p)
    except Exception:
        pass

    temp_total = scratch_size + screenshot_size + temp_jarvis_size
    total_size = mem_size + browser_cache_size + temp_total

    return {
        "total_bytes": total_size,
        "total_formatted": format_bytes(total_size),
        "memory_bytes": mem_size,
        "memory_formatted": format_bytes(mem_size),
        "facts_count": total_facts,
        "browser_cache_bytes": browser_cache_size,
        "browser_cache_formatted": format_bytes(browser_cache_size),
        "temp_bytes": temp_total,
        "temp_formatted": format_bytes(temp_total),
    }


def clear_browser_cache() -> int:
    """Cleans browser profiles and automation cache from ~/.jarvis_profiles."""
    home = Path.home()
    p = home / ".jarvis_profiles"
    freed = 0
    if p.exists():
        freed = _get_path_size(p)
        try:
            shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Storage] Error clearing browser cache: {e}")
    return freed


def clear_temp_files() -> int:
    """Cleans temporary files, desktop screenshots, and scratch items."""
    freed = 0
    home = Path.home()

    # Desktop screenshot
    sc = home / "Desktop" / "jarvis_screenshot.png"
    if sc.exists():
        try:
            freed += sc.stat().st_size
            sc.unlink(missing_ok=True)
        except Exception:
            pass

    # Scratch dir contents (keeps scratch dir itself)
    scratch = BASE_DIR / "scratch"
    if scratch.exists():
        for item in scratch.iterdir():
            try:
                freed += _get_path_size(item)
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass

    # Temp dir jarvis files
    temp_dir = Path(tempfile.gettempdir())
    try:
        for item in temp_dir.glob("jarvis_*"):
            freed += _get_path_size(item)
            if item.is_file():
                item.unlink(missing_ok=True)
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
    except Exception:
        pass

    return freed


def clear_memory(keep_identity: bool = False) -> int:
    """Clears long_term.json memory. If keep_identity is True, preserves name and language."""
    mem = load_memory()
    prev_size = _get_path_size(MEMORY_PATH)
    new_mem = _empty_memory()
    if keep_identity and "identity" in mem:
        new_mem["identity"] = mem["identity"]
    save_memory(new_mem)
    return max(0, prev_size - _get_path_size(MEMORY_PATH))


def clear_all_storage() -> Dict[str, Any]:
    """Clears browser cache, temporary files, and resets memory."""
    freed_cache = clear_browser_cache()
    freed_temp = clear_temp_files()
    freed_mem = clear_memory(keep_identity=False)
    total_freed = freed_cache + freed_temp + freed_mem
    return {
        "freed_bytes": total_freed,
        "freed_formatted": format_bytes(total_freed),
        "freed_cache": format_bytes(freed_cache),
        "freed_temp": format_bytes(freed_temp),
        "freed_memory": format_bytes(freed_mem),
    }
