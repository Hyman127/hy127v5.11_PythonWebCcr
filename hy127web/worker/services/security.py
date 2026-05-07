import os
import sys
from pathlib import Path

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _is_reserved_name(name: str) -> bool:
    base = os.path.splitext(name)[0].upper()
    return base in _WINDOWS_RESERVED


def _contains_null(path: str) -> bool:
    return "\0" in path


def validate_path(project_root: str, relative_path: str) -> bool:
    if not relative_path or not relative_path.strip():
        return False

    if _contains_null(relative_path):
        return False

    if os.path.isabs(relative_path):
        return False

    if sys.platform == "win32" and len(relative_path) >= 2 and relative_path[1] == ':':
        return False

    if relative_path.startswith('\\\\') or relative_path.startswith('//'):
        return False

    parts = relative_path.replace("\\", "/").split("/")
    for part in parts:
        if part in ("", ".", ".."):
            continue
        if _is_reserved_name(part):
            return False

    try:
        root = Path(project_root).resolve(strict=True)
        target = (root / relative_path).resolve()
    except (OSError, ValueError):
        return False

    if sys.platform == "win32":
        try:
            root_lower = str(root).lower().rstrip("\\")
            target_lower = str(target).lower().rstrip("\\")
            if not target_lower.startswith(root_lower + "\\") and target_lower != root_lower:
                return False
        except (OSError, ValueError):
            return False
    else:
        try:
            target.relative_to(root)
        except ValueError:
            return False

    actual = Path(project_root) / relative_path
    if actual.exists() and actual.is_symlink():
        try:
            link_target = actual.resolve()
            if sys.platform == "win32":
                link_target_lower = str(link_target).lower().rstrip("\\")
                root_lower = str(root).lower().rstrip("\\")
                if not link_target_lower.startswith(root_lower + "\\") and link_target_lower != root_lower:
                    return False
            else:
                link_target.relative_to(root)
        except ValueError:
            return False

    return True
