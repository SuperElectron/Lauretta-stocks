"""Every Valkey key and stream name the API and the worker share."""

JOBS = "jobs"
DEAD = "jobs:dead"
GROUP = "workers"
# One job entry carries its JSON under this field.
PAYLOAD = "payload"
# Where a pending-list scan starts, and the cursor returned once a scan reached the end.
SCAN_START = "0-0"


def job(job_id: str) -> str:
    """The job's status hash."""
    return f"job:{job_id}"


def events(job_id: str) -> str:
    """The job's event stream, read by SSE and by `?wait=`."""
    return f"job:{job_id}:events"


def thread_lock(thread_id: str) -> str:
    return f"lock:thread:{thread_id}"
