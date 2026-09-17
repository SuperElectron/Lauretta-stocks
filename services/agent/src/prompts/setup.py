"""The `<setup>` block: the first-run checklist and how to take the next step. `str.format`
fields; `NEXT_STEP` also takes the desk's current names (`{bot_name}` and the like)."""

MARKS = {"done": "✓", "skipped": "✓", "todo": "○"}
STEP_LINE = "{mark} {label}"
LABELS = {
    "investor_name": "What to call them (required)",
    "team_names": "Team names (optional)",
    "core_profile": "Core profile: goals, risk tolerance, time horizon, position limits, markets "
    "(required before any sizing)",
    "holdings": "Holdings (optional)",
}
MISSING = "; still unknown: {topics}"
NEXT = "Next step ({step}): {instruction}"
COMPLETE = "Setup is complete. Do not ask setup questions; help with what they ask."

NEXT_STEP = {
    "investor_name": "Ask what they'd like to be called, then save it with set_user_details.",
    "team_names": (
        "Offer to rename the team ({analyst_name}, {checker_name}, {strategist_name} and you, "
        "{bot_name}); they can keep the defaults. Save new names with set_identity. If they "
        "keep the names, call skip_setup_step with team_names."
    ),
    "core_profile": (
        "Ask about their {topic}, in plain words, and save the answer with remember. No examples "
        "of what they could say."
    ),
    "holdings": (
        "Ask what they hold: tickers, shares and average cost, and save each with set_holding. "
        "If they hold nothing or would rather not say, call skip_setup_step with holdings."
    ),
}
