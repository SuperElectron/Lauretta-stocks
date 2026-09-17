"""What the investor reads besides the assistant's own reply. `str.format` fields.

`TIMED_OUT` and `WAITING` are fixed notes: `api/openai/threads.py` never aliases a thread by them.
"""

STILL_WORKING = "Still working the trade. Give it a minute, then ask for the result."
TIMED_OUT = f"_({STILL_WORKING})_"
WAITING = (
    "Waiting on the desk to finish your last request; if it is still busy after half a minute, "
    "send again once it has answered.\n"
)
RETRYING = "\n\n_(retrying…)_\n\n"
ERROR = "The desk could not answer: {message}."
