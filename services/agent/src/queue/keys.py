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


def thread(user: str, thread_id: str) -> str:
    """The server-side key of a user's thread: the checkpoint's thread id. A user id holds no
    colon, so no two users' keys are ever equal, whatever thread id a client sends."""
    return f"{user}:{thread_id}"


def thread_lock(user: str, thread_id: str) -> str:
    return f"lock:thread:{thread(user, thread_id)}"


def request(digest: str) -> str:
    """A client request's idempotency record: `{job_id} {thread_id}` of the job it queued."""
    return f"oa:req:{digest}"


def thread_job(user: str, thread_id: str) -> str:
    """The job most recently queued on the user's thread."""
    return f"thread:{thread(user, thread_id)}:job"
