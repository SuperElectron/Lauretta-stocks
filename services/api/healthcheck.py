"""Container healthcheck: `python /app/healthcheck.py`. GET /healthz on the local uvicorn must
answer 200. Exits 0 when healthy, 1 otherwise. Never prints a URL or secret."""

import sys
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3) as resp:
            if resp.status != 200:
                raise RuntimeError(f"/healthz answered {resp.status}")
    except Exception as exc:
        print(f"unhealthy: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
