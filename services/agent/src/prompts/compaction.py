"""Compaction of long chat threads: the silent memory flush, the summary, and its block."""

FLUSH = """\
Older messages of this conversation are about to leave your view. Before they do, list every \
durable fact the investor stated about themselves in them: goals, rules, constraints, \
preferences, how they like to work, life events that affect their investing. One fact per item, \
in their terms, standalone and dated if it may change. Leave out anything about the assistant, \
market data, research results and small talk. Return an empty list when there is nothing \
durable. Save nothing else.

<already_remembered>
{remembered}
</already_remembered>

<messages>
{transcript}
</messages>"""

SUMMARY = """\
Write the running summary of this conversation between an investor and their research desk, \
for the desk to read before the recent messages. Keep: what the investor asked for and decided, \
open questions and promises the desk made, tickers discussed and what the desk concluded, and \
anything still being worked on. Leave out figures unless the investor stated them, and leave \
out small talk. Plain sentences, at most {max_words} words. Merge in the previous summary; drop \
what is settled and no longer matters.

<previous_summary>
{previous}
</previous_summary>

<messages>
{transcript}
</messages>"""

# In the assistant prompt, before the recent messages it summarises.
BLOCK = "<conversation_summary>\n{summary}\n</conversation_summary>"
