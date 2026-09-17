"""What the desk is called before the investor says otherwise, and what naming is still missing."""

# Every desk agent has a name the investor can change; the others are the defaults. No emoji.
IDENTITY_DEFAULTS: dict[str, str | None] = {
    "bot_name": "the Director",
    "analyst_name": "Andy",
    "checker_name": "Charlie",
    "strategist_name": "Sammy",
    "bot_emoji": None,
    "bot_vibe": "a sharp desk trader: direct, candid, professional",
    "tts_voice": None,
}
