"""What tools say to the model besides their data: notes, refusals and argument errors.

Tool descriptions stay as docstrings on the tools, which LangChain reads.
"""

NOT_REGISTERED = "no SEC registrant has this ticker; EDGAR covers US-listed shares and ADRs only"
NO_HOLDINGS = "No holdings recorded yet."
MIXED_CURRENCIES = "Values are in each listing's own currency; weights assume one currency."
NOTHING_TO_SET = "pass at least one field to set"
