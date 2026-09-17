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
- **Commands:** run `just` to list them all (`chat`, `research`, `up`, `down`, `test`, and `deploy`, `ps`, `logs`, `backup` for the Spark).
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
  a time, so each device or conversation should send its own `thread_id`. A stream that runs
  past `API_MAX_STREAM_S` ends with a `timeout` event; the job carries on, so reconnect to follow it.
- **Stream check:** `STREAM_CHECK_URL=http://127.0.0.1:8000 just stream-check` sends one
  message and reports how soon the first token arrived and how the rest trickled in. It fails
  if the first token takes more than 2s after the model starts, or if the tokens come in one
  lump. Set `STREAM_CHECK_API_KEY` when going through the gateway.
- **Chat apps:** the court also speaks the OpenAI Chat Completions dialect, so any chat app
  with an "OpenAI-compatible" provider may be admitted. See the next section.
- **How it works:** see `AGENTS.md`. For the original plan and open questions, see `.cache/PLAN.md` (local only, not committed).

## Chat apps (AnythingLLM and kin)

His Excellency need not learn a new instrument: any chat app with a Generic OpenAI provider
may petition the Director directly.

| Setting | Value |
|---|---|
| Base URL | `https://lauretta.tailae2b1.ts.net/v1` (or `http://127.0.0.1:8000/v1` locally) |
| API key | `GATEWAY_API_KEY` (anything, when calling the API directly) |
| Model | `lauretta` |
| Streaming | on |

- **Conversations:** the app sends no conversation id, so the court recognises a conversation
  by its first message. Apps that can send `X-Thread-Id` may name their own.
- **What is heard:** only the latest message. The app's own system prompt, attached documents
  and resent history are politely ignored; the court keeps its own minutes.
- **What is shown:** the team's comings and goings ("The Royal Analyst drafting…") arrive as
  reasoning, which most apps fold into a thought block; the answer arrives token by token.
- **Patience:** an app that retries a request, as the OpenAI SDKs do, rejoins the answer already
  under way; no research is run twice. Without streaming the court waits up to
  `API_MAX_WAIT_S`, then says it is still at work and to ask again.
- **Check it:** `just stream-check --openai` (see above) times the first reasoning and the first
  word through this door.
- **Not yet:** the app's own tools (agent skills) are not passed through; disable them.

## Running on the Spark

On the Mac the court sits at the kitchen table. On the DGX Spark it keeps residence full time:
the whole household runs in containers behind one guarded door, reachable only over the tailnet.

Before the first deploy, see that:

- the Spark runs Docker Engine 28 or newer (the gateway's healthcheck mounts an image volume);
- vLLM answers from inside a container at `host.docker.internal:8000` (listening on the host
  loopback alone is not enough);
- `DB_PASSWORD` and `BROKER_PASSWORD` are URL-safe (letters, digits, `-`, `_`), since they go
  into connection URLs;
- `~/lauretta-stocks` on the Spark is a clone of this repo with its own `.env`, and ssh with a
  key works (the recipes never prompt for a password).

```bash
just deploy             # from the Mac: git pull on the Spark, build natively, start the stack
just ps                 # who is at their post
just logs worker        # what the worker is muttering (omit the name for everyone)
just backup             # a database dump now, into backups/ on the Spark
```

- **The door:** AgentGateway (`ops/gateway/config.yaml`). `/v1` and everything under it need
  `Authorization: Bearer $GATEWAY_API_KEY`; `/healthz` is open; any other path is 404. It strips
  the key and any claimed identity (including Tailscale's and forwarding headers) before the api
  sees the request, rate limits, and never buffers, so streams arrive as they are written. It
  alone holds the provider keys.
- **The tailnet:** the court lives at `https://lauretta.tailae2b1.ts.net`. The `tailscale`
  container joins the tailnet as `lauretta-host` (`tag:lauretta`) and hosts the Tailscale Service
  `svc:lauretta`, with a real certificate, straight to the gateway. There is nothing to expose by
  hand: `just deploy` brings it up. Only the owner and His Excellency can reach it, by tailnet
  policy; Funnel is off. The Spark's `.env` needs `TS_OAUTH_SECRET` (the OAuth client secret,
  copied from the owner's Mac at deploy). The service withdraws when the container stops and
  returns about 20 seconds after it starts. If the `tsstate` volume is ever wiped, delete the old,
  offline `lauretta-host` device in the admin console.
- **Models:** api and worker ask the gateway's internal `llm` port for `gpt-oss-120b` (vLLM on the
  Spark) or `openai/gpt-oss-120b` (OpenRouter). Failover between them is issue #4.
- **Backups:** the `backup` service dumps the database when it starts and at 03:00 UTC into
  `backups/`, keeps the newest `BACKUP_KEEP`, and turns unhealthy after 26 hours without a dump.
  Restore with `pg_restore`.
- **Gotchas:** the gateway's `requestTimeout` bounds only the time to response headers, not a
  stream; `csrf` is not authentication; and the gateway expands `${...}` even in config comments.

| Port | Bound to | Serves |
|---|---|---|
| 443 on `lauretta.tailae2b1.ts.net` | tailnet only (`svc:lauretta`) | HTTPS to the gateway |
| 18400, 3000, 8000, 5432, 6379 | compose network only | gateway ingress and `llm`, api, db, broker |

The stack publishes no host ports at all. The Spark's own ports (8000-8004 and friends) are left alone; vLLM
is reached from inside at `host.docker.internal:8000`. For local development, `just up` still
starts only the database, on loopback `DB_PORT`.
