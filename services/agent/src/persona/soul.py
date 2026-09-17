"""Checks a soul text against the cap. The wording lives in `prompts/soul.py`."""

from src.errors import PersonaInvalid
from src.prompts.soul import SOUL_MAX_CHARS


def check_soul(text: str) -> str:
    """The soul text, stripped, or `PersonaInvalid` when it is empty or over the cap."""
    stripped = text.strip()
    if not stripped:
        raise PersonaInvalid("the soul is empty")
    if len(stripped) > SOUL_MAX_CHARS:
        raise PersonaInvalid(f"the soul is {len(stripped)} chars; the cap is {SOUL_MAX_CHARS}")
    return stripped
