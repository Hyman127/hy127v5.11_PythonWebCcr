#!/usr/bin/env python3
"""Export FastAPI route tables from Hub and Worker apps as a Markdown checklist.

Usage:
    python scripts/export_routes.py          # print all routes
    python scripts/export_routes.py --json   # JSON output
    python scripts/export_routes.py --check  # checklist format with [ ] checkboxes
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AUTH_ANNOTATIONS = {
    "require_launch_token": "launch_token",
    "require_session": "session",
    "require_csrf": "session+csrf",
}


def _auth_required(route) -> str:
    """Heuristic: inspect the endpoint function source or closed-over auth calls."""
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        return ""
    try:
        src = __import__("inspect").getsource(endpoint)
    except (OSError, TypeError):
        return ""
    if "require_csrf" in src:
        return "session+csrf"
    if "require_session" in src:
        return "session"
    if "require_launch_token" in src:
        return "launch_token"
    return "none"


def collect_routes(app, source: str) -> list[dict]:
    routes = []
    for route in app.routes:
        if not hasattr(route, "methods") or not route.methods:
            continue
        path = getattr(route, "path", "")
        for method in sorted(route.methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.append({
                "method": method,
                "path": path,
                "name": getattr(route, "name", ""),
                "auth": _auth_required(route),
                "source": source,
            })
    routes.sort(key=lambda r: (r["source"], r["path"], r["method"]))
    return routes


def main():
    parser = argparse.ArgumentParser(description="Export Hy127 Web route tables")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check", action="store_true", help="Checklist format")
    args = parser.parse_args()

    # Import apps (module-level side-effects are safe since we're just introspecting routes)
    try:
        from hy127web.hub.app import app as hub_app
    except ImportError as e:
        print(f"Error importing Hub: {e}", file=sys.stderr)
        print("Make sure fastapi and project dependencies are installed.", file=sys.stderr)
        sys.exit(1)
    from hy127web.worker.app import app as worker_app

    hub_routes = collect_routes(hub_app, "Hub")
    worker_routes = collect_routes(worker_app, "Worker")
    all_routes = hub_routes + worker_routes

    if args.json:
        print(json.dumps(all_routes, ensure_ascii=False, indent=2))
        return

    if args.check:
        for r in all_routes:
            auth_tag = f"[{r['auth']}]" if r["auth"] and r["auth"] != "none" else ""
            print(f"- [ ] {r['method']:6} {r['path']:50} {auth_tag}")
        return

    # Default: Markdown table
    print("## Hub Routes\n")
    print("| Method | Path | Auth |")
    print("|--------|------|------|")
    for r in hub_routes:
        auth = r["auth"] if r["auth"] != "none" else ""
        print(f"| {r['method']} | {r['path']} | {auth} |")

    print("\n## Worker Routes\n")
    print("| Method | Path | Auth |")
    print("|--------|------|------|")
    for r in worker_routes:
        auth = r["auth"] if r["auth"] != "none" else ""
        print(f"| {r['method']} | {r['path']} | {auth} |")

    print(f"\nTotal: {len(hub_routes)} Hub routes, {len(worker_routes)} Worker routes")


if __name__ == "__main__":
    main()
