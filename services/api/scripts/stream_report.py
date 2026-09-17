"""What `stream_check.py` prints about a stream's timings, its verdict, and how it tells the
desk's own reasoning lines from the model's."""

import re

from src.prompts import progress

# Tokens this many or more, all within this window, came as one burst, not a stream.
BURST_TOKENS = 5
BURST_SECONDS = 0.05


def template(text: str, **fields: str) -> str:
    """A `str.format` template from `src/prompts` as a regex; unnamed fields match any text."""
    parts = re.split(r"\{(\w+)\}", text)
    return "".join(
        re.escape(part) if i % 2 == 0 else fields.get(part, ".+") for i, part in enumerate(parts)
    )


# The desk's own reasoning lines (progress and tool steps, as `chunks.py` sends them, with a
# newline first after the model's thinking); anything else is the model's own reasoning. Names
# are the investor's to change, so any name matches; the role must be one of the desk's.
_ROLES = "|".join(re.escape(role) for role in progress.ROLES.values())
_DETAILS = (progress.ASSISTANT_WORKING, progress.ASSISTANT_RETRYING, progress.SAVING)
_OWN = "|".join(re.escape(detail) for detail in _DETAILS)
_ROLE_DETAILS = (progress.ANALYST_DRAFTING, progress.ANALYST_REDRAFTING, progress.CHECKER_CHECKING,
                 progress.CHECKER_VERDICT, progress.STRATEGIST_SIZING)  # fmt: skip
_WORK = "|".join(template(detail) for detail in _ROLE_DETAILS)
_LINES = [
    template(progress.ROLE_LINE, role=f"(?:{_ROLES})", detail=f"(?:{_WORK})"),
    template(progress.LINE, detail=f"(?:{_OWN})"),
]
_LINES += [template(line) for line in progress.TOOL.values()]
DESK_LINE = re.compile(r"\n?(?:" + "|".join(_LINES) + r")\n")
# The Director's first line of a turn, whatever it is called.
MODEL_START = re.compile(template(progress.LINE, detail=re.escape(progress.ASSISTANT_WORKING)))


def report(what: str, at: float | None, model_start: float | None) -> None:
    if at is None or model_start is None:
        print(f"{what}: none")
    else:
        print(f"{what} {at - model_start:.3f}s after model start")


def verdict(model_start: float | None, stamps: list[float], failed: bool = False) -> int:
    """Reports the first content token (not gated) and fails a stream that came in one burst."""
    if model_start is None or not stamps:
        print("FAIL: no model start or no tokens were streamed")
        return 1
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    first = stamps[0] - model_start
    print(f"tokens: {len(stamps)}; first content token {first:.3f}s after model start")
    if gaps:
        median, largest = sorted(gaps)[len(gaps) // 2], max(gaps)
        print(f"gaps between tokens: median {median * 1000:.1f}ms, max {largest * 1000:.1f}ms")
    if len(stamps) >= BURST_TOKENS and stamps[-1] - stamps[0] < BURST_SECONDS:
        print(f"FAIL: all {len(stamps)} tokens arrived within {BURST_SECONDS * 1000:.0f}ms")
        failed = True
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0
