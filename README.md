# Lauretta Stocks

By appointment to **His Excellency Max Lauretta**, Sovereign of the Portfolio, Defender of
the Dividend and Keeper of the Long Position, this humble establishment offers a research
court for the running of his financial empire.

A sovereign should not squint at 10-K filings by candlelight. Lauretta Stocks gives to whom it concerns a
small, tireless court of advisers:

- **The Director** (chat assistant) remembers His Excellency's preferences, his appetite for
  risk and every holding in the treasury, so nothing need be said twice.
- **The Royal Analyst** reads the filings and the market, then writes a stock story: what the
  company does, what could move it, what the market has missed, the date of reckoning, and
  what would prove the whole thing wrong.
- **The Inspector General** trusts nobody, re-checks every figure, and sends shoddy work back
  to be done properly.
- **The Privy Counsellor** weighs the story against the treasury and suggests whether to buy,
  hold, trim or sell. It suggests; His Excellency decides. No trade is ever placed on his
  behalf, and nothing here is financial advice.

All data comes from free sources (SEC EDGAR and Yahoo Finance), because an empire is built by
not wasting the crown's money.

## TLDR

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY and SEC_USER_AGENT="Your Name you@example.com"
just up                 # start the database
just chat               # speak with the court
just research MSFT      # summon the full research team on one stock
```

## Details

- **Needs:** Docker, [uv](https://docs.astral.sh/uv/) and [just](https://just.systems).
- **Commands:** run `just` to list them all (`chat`, `research`, `up`, `down`, `test`).
- **Model:** Claude through the Anthropic API by default. The API key is billed separately from a
  Claude Pro subscription. Any OpenAI-compatible server also works (`AGENT_PROVIDER=openai`).
- **Reports:** `just research` saves a one-page report to `reports/`.
- **First run:** downloads a small embedding model (about 70 MB) for memory search.
- **Start fresh:** `just down clean=true` wipes memories, holdings and past research.
- **The API:** for His Excellency's telephone and other distant devices, `just broker`,
  `just api` and `just worker` run the court as a service. `POST /v1/jobs` queues a chat turn
  (`{"kind": "chat", "message": "..."}`) or a research run (`{"kind": "research", "ticker":
  "MSFT"}`) and answers `202` with an `events_url`, which streams the reply token by token as
  server-sent events (`curl -N`). Add `?wait=25` to simply wait for the answer instead.
  A chat without a `thread_id` joins the thread `main`, and one thread answers one message at
  a time, so each device or conversation should send its own `thread_id`.
- **Stream check:** `STREAM_CHECK_URL=http://127.0.0.1:8000 just stream-check` sends one
  message and reports how soon the first token arrived and how the rest trickled in. It fails
  if the first token takes more than 2s after the model starts, or if the tokens come in one
  lump. Set `STREAM_CHECK_API_KEY` when going through the gateway.
- **How it works:** see `AGENTS.md`. For the original plan and open questions, see `.cache/PLAN.md` (local only, not committed).
