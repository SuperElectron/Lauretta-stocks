"""What the assistant is before the investor says otherwise, and what naming is still missing."""

# The assistant is the Director until the investor renames it. No emoji by default.
IDENTITY_DEFAULTS: dict[str, str | None] = {
    "bot_name": "the Director",
    "bot_emoji": None,
    "bot_vibe": "a sharp desk trader: direct, candid, professional",
    "tts_voice": None,
}

# The `<unnamed>` items, in the order the assistant asks about them. With the default name set,
# only the investor's name is ever missing.
UNNAMED_BOT = "what the investor wants to call you"
UNNAMED_USER = "what to call the investor"
