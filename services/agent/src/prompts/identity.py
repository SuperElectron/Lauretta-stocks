"""What the desk is called before the investor says otherwise, and what naming is still missing."""

# Every desk agent has a name the investor can change; the others are the defaults. No emoji.
IDENTITY_DEFAULTS: dict[str, str | None] = {
    "bot_name": "the Director",
    "analyst_name": "Nate",
    "auditor_name": "Vera",
    "strategist_name": "Marcus",
    "bot_emoji": None,
    "bot_vibe": "a sharp desk trader: direct, candid, professional",
    "tts_voice": None,
}

# The `<unnamed>` item: every agent has a default name, so only the investor's can be missing.
UNNAMED_USER = "what to call the investor"
