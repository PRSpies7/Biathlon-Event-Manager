from __future__ import annotations

import re


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def event_results_filename(event_name: object, extension: str) -> str:
    """Return a Windows-safe final-results filename using the stored event name."""
    name = _INVALID_FILENAME_CHARS.sub("_", str(event_name or "")).strip(" .")
    if not name or name.upper() in _WINDOWS_RESERVED_NAMES:
        name = "Event"
    return f"{name} Master Results.{extension.lstrip('.')}"
