"""ReasoningFilter: what of the model's reasoning may be streamed, however it is fragmented."""

import pytest

from src.worker.redact import MAX_HOLDS, REDACTED, ReasoningFilter, identifying_values


def test_the_filter_redacts_values_split_across_fragments_and_holds_back_only_a_tail():
    guard = ReasoningFilter(["New York", "api"])
    sent = [guard.feed(piece) for piece in ("Seen near New ", "York through the ", "api today ")]
    sent.append(guard.flush())
    assert "".join(sent) == f"Seen near {REDACTED} through the {REDACTED} today "
    assert "".join(sent[:2]).startswith("Seen near")
    assert ReasoningFilter(["api"]).flush() == ""
    words = ReasoningFilter(["api"])
    assert words.feed("apis rapid api") + words.flush() == f"apis rapid {REDACTED}"


def test_only_identifying_signals_are_redacted_so_ordinary_words_survive():
    rows = [
        {"kind": "signal", "key": "channel", "value": "api"},
        {"kind": "signal", "key": "client", "value": "phone"},
        {"kind": "signal", "key": "ip", "value": "100.64.0.7"},
        {"kind": "profile", "key": "city", "value": "London"},
    ]
    guard = ReasoningFilter(identifying_values(rows))
    text = "Via the api on their phone from 100.64.0.7 in London."
    assert (
        guard.feed(text) + guard.flush() == f"Via the api on their phone from {REDACTED} in London."
    )


@pytest.mark.parametrize(
    "pieces", [["ab. New Yo", "rk. and more…"], ["In New Yo", "rk today"]], ids=["dot", "short"]
)
def test_a_value_split_across_short_fragments_is_still_redacted(pieces):
    guard = ReasoningFilter(["New York"])
    sent = "".join(guard.feed(piece) for piece in pieces) + guard.flush()
    assert "New" not in sent and "York" not in sent and REDACTED in sent


def test_values_are_redacted_in_any_case():
    guard = ReasoningFilter(["London"])
    sent = guard.feed("LONDON or london or London, not Londoner. ") + guard.flush()
    assert sent == f"{REDACTED} or {REDACTED} or {REDACTED}, not Londoner. "


def test_a_long_run_without_whitespace_is_sent_before_the_flush_and_stays_bounded():
    guard = ReasoningFilter(["100.64.0.7"])
    sent = [guard.feed("x" * 100) for _ in range(200)]
    assert sent[1] and len(guard._buffer) <= MAX_HOLDS * guard._hold + 100
    assert "".join(sent) + guard.flush() == "x" * 20_000


@pytest.mark.parametrize(
    "tag", ["<theses>", "</unknown>", "<unnamed>", "<stage>", "</soul_change>", "<signals id=1>"]
)
def test_pieces_quoting_any_prompt_tag_are_dropped(tag):
    guard = ReasoningFilter([])
    sent = guard.feed(f"the {tag} block ") + guard.feed(" " * 40 + "ok ") + guard.flush()
    assert "<" not in sent and "block" not in sent and sent.endswith("ok ")


def test_the_filter_drops_pieces_quoting_prompt_blocks_and_strips_think_tags():
    guard = ReasoningFilter([])
    text = "The <sig" + "nals> block says so. " + "x" * 40 + " <think>fine</think> end"
    sent = guard.feed(text) + guard.flush()
    assert "signals" not in sent and "block says" not in sent
    assert sent.endswith("fine end") and "think" not in sent
