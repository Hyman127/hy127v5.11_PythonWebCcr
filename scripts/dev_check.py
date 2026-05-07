#!/usr/bin/env python3
"""Validate that all required Python packages are installed for development.

Usage:
    python scripts/dev_check.py
"""

import importlib.util
import sys

required = ["fastapi", "uvicorn", "httpx", "pytest"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Suggested:")
    print("  python -m pip install -r hy127web/requirements.txt pytest")
    sys.exit(1)
print("dev dependencies ok")
