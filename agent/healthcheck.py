"""Container healthcheck: `python /app/healthcheck.py api|worker`.

api: GET /healthz on the local uvicorn must answer 200.
worker: Postgres and the broker answer, and a `python -m src.worker` process is running.
Exits 0 when healthy, 1 otherwise, naming the failed check. Never prints a URL or secret.
"""

import os
import sys
import urllib.request


def _check_api() -> None:
    with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3) as resp:
        if resp.status != 200:
            raise RuntimeError(f"/healthz answered {resp.status}")


def _check_postgres() -> None:
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
        conn.execute("SELECT 1")


def _check_broker() -> None:
    import redis

    client = redis.from_url(os.environ["BROKER_URL"], socket_timeout=3)
    try:
        client.ping()
    finally:
        client.close()


def _check_worker_process() -> None:
    me = str(os.getpid())
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or pid == me:
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
        except OSError:
            continue
        if len(argv) >= 3 and argv[1] == b"-m" and argv[2] == b"src.worker":
            return
    raise RuntimeError("worker process not running")


CHECKS = {
    "api": (("api", _check_api),),
    "worker": (
        ("postgres", _check_postgres),
        ("broker", _check_broker),
        ("worker", _check_worker_process),
    ),
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        print("usage: healthcheck.py api|worker")
        return 1
    for name, check in CHECKS[sys.argv[1]]:
        try:
            check()
        except Exception as exc:
            print(f"healthcheck failed: {name} ({type(exc).__name__})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
