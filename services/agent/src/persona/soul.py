"""Checks a soul text against the cap and the prompt's block tags."""

from src.errors import PersonaInvalid

# The soul is prompt text on every turn; this keeps a proposal from crowding out the rest.
SOUL_MAX_CHARS = 4000

SOUL_EMPTY = "the soul is empty"
SOUL_TOO_LONG = "the soul is {chars} chars; the cap is {cap}"
SOUL_ANGLE_BRACKETS = "the soul contains < or >"


def check_soul(text: str) -> str:
    """The soul text, stripped, or `PersonaInvalid` when it is empty, over the cap or holds `<` or
    `>` (it is rendered inside the prompt's `<soul>` block)."""
    stripped = text.strip()
    if not stripped:
        raise PersonaInvalid(SOUL_EMPTY)
    if len(stripped) > SOUL_MAX_CHARS:
        raise PersonaInvalid(SOUL_TOO_LONG.format(chars=len(stripped), cap=SOUL_MAX_CHARS))
    if "<" in stripped or ">" in stripped:
        raise PersonaInvalid(SOUL_ANGLE_BRACKETS)
    return stripped
