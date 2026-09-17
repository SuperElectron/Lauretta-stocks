"""The default name of the agent behind each job stage, for progress events sent without one.
Mirrors the worker's identity defaults; `contracts/job_events.v1.json` pins both."""

NAMES_BY_STAGE: dict[str, str] = {
    "assistant": "the Director",
    "save": "the Director",
    "analyst": "Andy",
    "checker": "Charlie",
    "advisor": "Sammy",
}


def default_name(stage: str) -> str | None:
    return NAMES_BY_STAGE.get(stage)
