import os
from pathlib import Path


def validate_path(project_root: str, relative_path: str) -> bool:
    if not relative_path or not relative_path.strip():
        return False

    if os.path.isabs(relative_path):
        return False

    if len(relative_path) >= 2 and relative_path[1] == ':':
        return False

    if relative_path.startswith('\\\\') or relative_path.startswith('//'):
        return False

    try:
        root = Path(project_root).resolve(strict=True)
        target = (root / relative_path).resolve()
    except (OSError, ValueError):
        return False

    try:
        target.relative_to(root)
    except ValueError:
        return False

    actual = Path(project_root) / relative_path
    if actual.exists() and actual.is_symlink():
        link_target = actual.resolve()
        try:
            link_target.relative_to(root)
        except ValueError:
            return False

    return True
