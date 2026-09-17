"""Typed API errors. Each carries a code; the messages live in `prompts/errors.py`."""

from src.prompts import errors as wording


class ApiError(Exception):
    code = "INTERNAL_ERROR"
    message = wording.JOB_FAILED

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class DatabaseUnavailable(ApiError):
    code = "DATABASE_UNAVAILABLE"
    message = wording.DATABASE_UNAVAILABLE


class NoUser(ApiError):
    """A query on user data without the user it acts for; nothing is read or written."""

    code = "NO_USER"
    message = wording.NO_USER
