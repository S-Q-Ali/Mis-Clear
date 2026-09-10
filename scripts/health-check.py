"""Health check for the running Privacy Guardian backend (local only)."""

import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def main() -> int:
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        print(body)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())