"""What a memory is about. The core topics are the investor profile the advisor needs."""

from typing import Literal, get_args

Topic = Literal[
    "goals",
    "risk_tolerance",
    "time_horizon",
    "position_limits",
    "markets",
    "sectors",
    "account_and_tax",
    "experience",
    "preference",
    "lesson",
    "other",
]

# Without these the advisor will not size a position.
CORE_TOPICS: tuple[Topic, ...] = (
    "goals",
    "risk_tolerance",
    "time_horizon",
    "position_limits",
    "markets",
)
TOPICS: tuple[Topic, ...] = get_args(Topic)
