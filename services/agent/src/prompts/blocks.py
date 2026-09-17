"""The words inside data blocks: empty states and line formats. `str.format` fields."""

NOT_SET = "not set"
NO_SIGNALS = "none"
NO_INVESTOR_FACTS = "nothing yet"
NO_HOLDINGS = "none recorded"
NO_THESES = "none yet"
NOTHING_UNKNOWN = "nothing"

SIGNAL_LINE = "{key}: {value} (since {since})"
INVESTOR_LINE = "{topic}: {content} ({created}, id {id})"
THESIS_LINE = "{ticker}: {action} ({verdict} by the Auditor), {created}"
