"""How each single-valued fact reads, as stored and embedded and later shown to the model.

`{}` is the value. Changing a sentence changes only facts written after the change.
"""

SENTENCES = {
    "bot_name": "The investor calls the assistant {}.",
    "analyst_name": "The investor calls the Analyst {}.",
    "auditor_name": "The investor calls the Auditor {}.",
    "strategist_name": "The investor calls the Strategist {}.",
    "bot_emoji": "The assistant's emoji is {}.",
    "bot_vibe": "The assistant's manner is: {}.",
    "tts_voice": "The assistant speaks with the {} voice.",
    "name": "The investor's name is {}.",
    "preferred_name": "The investor wants to be called {}.",
    "city": "The investor lives in {}.",
    "country": "The investor's country is {}.",
    "currency": "The investor counts money in {}.",
    "timezone": "The investor's timezone is {}.",
    "ip": "Last connected from IP address {}.",
    "client": "Last connected with the {} app.",
    "channel": "Last spoke through the {} channel.",
    "last_seen_city": "Last seen near {}.",
}
