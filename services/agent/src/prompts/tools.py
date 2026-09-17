"""What tools say to the model besides their data: notes, refusals and argument errors.

Tool descriptions stay as docstrings on the tools, which LangChain reads.
"""

NOT_REGISTERED = "no SEC registrant has this ticker; EDGAR covers US-listed shares and ADRs only"
NO_HOLDINGS = "No holdings recorded yet."
MIXED_CURRENCIES = "Values are in each listing's own currency; weights assume one currency."
NOTHING_TO_SET = "pass at least one field to set"
ANGLE_BRACKETS = (
    "must not contain < or >, which would break the prompt's blocks; name a block without them"
)
TOO_MANY_PROPOSALS = (
    "not proposed: {cap} soul proposals already wait for the investor's decision; ask them to "
    "approve or reject one first"
)
