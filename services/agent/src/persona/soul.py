"""Checks a soul text against the cap and the prompt's block tags. The wording lives in
`prompts/`."""

from src.errors import PersonaInvalid
from src.prompts import errors
from src.prompts.soul import SOUL_MAX_CHARS


def check_soul(text: str) -> str:
    """The soul text, stripped, or `PersonaInvalid` when it is empty, over the cap or holds `<` or
    `>` (it is rendered inside the prompt's `<soul>` block)."""
    stripped = text.strip()
    if not stripped:
        raise PersonaInvalid(errors.SOUL_EMPTY)
    if len(stripped) > SOUL_MAX_CHARS:
        raise PersonaInvalid(errors.SOUL_TOO_LONG.format(chars=len(stripped), cap=SOUL_MAX_CHARS))
    if "<" in stripped or ">" in stripped:
        raise PersonaInvalid(errors.SOUL_ANGLE_BRACKETS)
    return stripped
