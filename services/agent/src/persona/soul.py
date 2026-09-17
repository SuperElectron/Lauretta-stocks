"""Checks a soul text against the cap. The wording lives in `prompts/soul.py`."""

from src.errors import PersonaInvalid
from src.prompts import notes
from src.prompts.soul import SOUL_MAX_CHARS


def check_soul(text: str) -> str:
    """The soul text, stripped, or `PersonaInvalid` when it is empty or over the cap."""
    stripped = text.strip()
    if not stripped:
        raise PersonaInvalid(notes.SOUL_EMPTY)
    if len(stripped) > SOUL_MAX_CHARS:
        raise PersonaInvalid(notes.SOUL_TOO_LONG.format(chars=len(stripped), cap=SOUL_MAX_CHARS))
    return stripped
