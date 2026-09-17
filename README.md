# Lauretta Stocks

A research desk for Max Lauretta's book: it learns how he invests, keeps every position on the
sheet, runs a three-person research team on any ticker he names, and calls it straight. It
never places a trade. It suggests; he pulls the trigger.

Behind it sits a trading desk straight from the bullpen: cool, direct and professional, always
working for the best risk-adjusted outcome for the portfolio and blunt about the downside.

- **The Director** (the chat assistant) runs the desk: remembers the investor's preferences,
  their appetite for risk and every holding in the book, leads with the call and then the why,
  and says plainly what would make it wrong.
- **Andy, the Analyst**, reads the filings and the market, then writes a stock story: what the
  company does, what could move it, what the market has missed, the dated catalyst, and what
  would prove the whole thing wrong.
- **Charlie, the Checker**, trusts nobody, re-checks every figure, and sends the story back until
  the numbers hold up.
- **Sammy, the Strategist**, sizes the story against the book and suggests whether to buy, add,
  hold, trim or sell. It suggests; the investor decides. No trade is ever placed on their
  behalf, and nothing here is financial advice.

Those are the default names. Any of them can be renamed in chat ("call the Analyst Sarah"); the
new name is kept in the investor's memory and used from then on, in replies, progress lines and
reports.

On first contact the Director introduces its team and walks the investor through a short setup,
one question per reply: what to call them, whether to rename the team (optional), the core
profile the Strategist needs before it sizes anything (goals, risk tolerance, time horizon,
position limits, markets), then current holdings (optional). Skipped steps stay skipped, and a
real question is always answered first.

```
Investor: should I sell my Shell?
Director: Here's the read: hold, not sell. Charlie approved the story but flagged refining margins
          as the swing factor, and Sammy would change the call if Q3 cash flow comes in under
          dividend plus buybacks on 30 October. This is a suggestion, not financial advice.
```

All data comes from free sources (SEC EDGAR and Yahoo Finance): no paid feed without the
owner's say-so.

## TLDR

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY and SEC_USER_AGENT="Your Name you@example.com"
just up                 # start the database
just chat               # talk to the desk
just research MSFT      # put the whole desk on one stock
```

## Details

- **Needs:** Docker, [uv](https://docs.astral.sh/uv/) and [just](https://just.systems).
- **Commands:** run `just` to list them all (`chat`, `research`, `up`, `down`, `test`, and `deploy`, `ps`, `logs`, `backup` for the Spark).
- **Model:** Claude through the Anthropic API by default. The API key is billed separately from a
  Claude Pro subscription. Any OpenAI-compatible server also works (`AGENT_PROVIDER=openai`).
- **Reports:** `just research` saves a one-page report to `reports/`.
- **First run:** downloads a small embedding model (about 70 MB) for memory search.
- **Start fresh:** `just down clean=true` wipes memories, holdings and past research.
- **The API:** for phones and other devices, `just broker`,
  `just api` and `just worker` run the desk as a service. `POST /v1/jobs` queues a chat turn
  (`{"kind": "chat", "message": "..."}`) or a research run (`{"kind": "research", "ticker":
  "MSFT"}`) and answers `202` with an `events_url`, which streams the reply token by token as
  server-sent events (`curl -N`). Add `?wait=25` to simply wait for the answer instead.
  A chat without a `thread_id` joins the thread `main`, and one thread answers one message at
  a time, so each device or conversation should send its own `thread_id`. A stream that runs
  past `API_MAX_STREAM_S` ends with a `timeout` event; the job carries on, so reconnect to follow it.
- **Stream check:** `STREAM_CHECK_URL=http://127.0.0.1:8000 just stream-check` sends one
  message and reports how soon the model's first reasoning and first token arrived and how the
  rest trickled in. It fails if the model shows nothing (reasoning or token) for more than 2s
  after it starts, or if the tokens come in one lump; the first token is reported, not gated,
  since a reasoning model thinks first. Set `STREAM_CHECK_API_KEY` when going through the
  gateway. The events stream sends the model's own thinking as `reasoning` events, apart from
  its `token`s; it is never part of the reply. It is unverified model thinking: figures there are
  not sourced. The investor's network address and last seen place are redacted from it,
  and `AGENT_STREAM_REASONING=false` turns it off.
- **Chat apps:** the desk also speaks the OpenAI Chat Completions dialect, so any chat app
  with an "OpenAI-compatible" provider can connect. See the next section.
- **How it works:** see `AGENTS.md`. For the original plan and open questions, see `.cache/PLAN.md` (local only, not committed).

## Chat apps (AnythingLLM and kin)

No new app to learn: any chat app with a Generic OpenAI provider can reach the desk directly.

| Setting | Value |
|---|---|
| Base URL | `https://lauretta.tailae2b1.ts.net/v1` (or `http://127.0.0.1:8000/v1` locally) |
| API key | `GATEWAY_API_KEY`, the owner's key (acts as `mat`) |
| Model | `lauretta-<user>`, the caller's own: `lauretta-mat` with the owner's key |
| Streaming | on |

Calling the API directly (locally, no gateway) needs the header the gateway would set,
`X-Lauretta-User: mat`, instead of a key. See [Users and isolation](#users-and-isolation).

- **Conversations:** the app sends no conversation id, so the desk recognises a conversation
  by the history it resends: each prompt and answer it has seen points back to its thread, so
  a long conversation keeps its thread after the first message scrolls out of the window. A
  message with no history opens a new conversation, even when it says "hi" like the last one.
  Apps that can send `X-Thread-Id` may name their own.
- **What is heard:** only the latest message. The app's own system prompt, attached documents
  and resent history are ignored; the desk keeps its own record.
- **What is shown:** the team's comings and goings ("Andy (Analyst) drafting the story…", "Charlie
  (Checker) re-checking the numbers…") and the desk model's own thinking arrive as reasoning,
  which most apps fold into a thought block; the answer arrives token by token. The thinking is
  unverified model thinking: figures there are not sourced, and only the answer holds to the
  desk's rules.
- **Patience:** an app that retries a request within 15 minutes, as the OpenAI SDKs do, rejoins
  the answer already under way; no research is run twice. Once an answer has been delivered, or
  if the turn failed, the same request is a new turn (a regenerate or a resend). A message sent
  while the previous one is still being answered says at once that it is waiting; if the desk
  is still busy after half a minute it gives up, so send it again once the answer has arrived. Without
  streaming the desk waits up to `API_MAX_WAIT_S`, then says it is still working: wait a
  minute, then ask for the result.
- **Check it:** `just stream-check --openai` (see above) times the first reasoning, the model's
  own first reasoning and the first word through this endpoint. It passes when the first
  reasoning comes within 1s and the words trickle in; the first word is reported, not gated.
- **Not yet:** the app's own tools (agent skills) are not passed through; disable them.

## Talking to the desk

No `curl` needed. The desk is reached through [AnythingLLM](https://anythingllm.com), a chat
web app with threads, where the desk answers.

- **The web app:** open https://lauretta.tailae2b1.ts.net on any device on the tailnet. Any browser
  will do, the iPhone's included.
- **The first visit** (the owner, straight after the first deploy): AnythingLLM asks for a password,
  which is `ANYTHINGLLM_AUTH_TOKEN` from the Spark's `.env`. Then, in Settings > Security, turn on
  multi-user mode and create the admin account, and in Settings > Users (under Admin) create
  the investor's with the role **Default** (not Admin or Manager). From then on everyone signs
  in with their own account and the password is no longer used. Until this is done, whoever
  holds the password holds the app, so do it at once. Then give each person their own
  workspace (see [Users and isolation](#users-and-isolation)).
- **The Android app:** install AnythingLLM from Google Play. In AnythingLLM (opened at the tailnet
  address, not `localhost`), go to Settings > AnythingLLM Mobile and scan its QR code with the
  app. The phone must be on the tailnet too. There is no iPhone app; the browser serves.
- **Documents:** AnythingLLM accepts uploads (up to 100 MiB each), but **the desk does not read
  them yet**: the desk's endpoint ignores the context AnythingLLM retrieves from them.
- **How it connects:** AnythingLLM comes preset as the [chat app](#chat-apps-anythingllm-and-kin)
  described above, with its own key, `ANYTHINGLLM_API_KEY`: each person's workspace asks the
  gateway's `/v1` for their own model (`lauretta-mat`, `lauretta-max`), which is how the desk
  knows who is chatting. It takes the plain streaming chat path (no agent tools). It sits on its own `web` network with the gateway alone and can reach nothing else in
  the stack. It keeps its chats, accounts and documents in the `anythingllm` volume.
- **What it fetches from the internet:** at boot, LiteLLM's model map (GitHub) and model prices
  (models.dev); on the first document, its embedding model, once. None of it carries user data.

## MCP clients (Goose and kin)

The desk is also an MCP server (streamable HTTP) at `https://lauretta.tailae2b1.ts.net/mcp/`, for
Goose and other MCP clients on the tailnet. It takes the owner's key only (`GATEWAY_API_KEY`, as
`Authorization: Bearer <key>`) and acts as `mat`; AnythingLLM's key is refused.

- **Tools:** `ask_assistant(message, thread_id="mcp")`, `research_stock(ticker)` (waits, with
  MCP progress notifications per step), `start_research(ticker)` and `get_job(job_id)` (without
  waiting), `get_thesis(ticker)`, `holdings()`.
- **Goose:** add a remote extension of type *Streamable HTTP* with that URL and the header
  `Authorization: Bearer <GATEWAY_API_KEY>`.
- **How it runs:** inside api (`src/api/mcpserver/`), stateless, over the same jobs, queue and
  reads as `/v1`; the gateway names the user exactly as for `/v1`.

## Voice

Speech runs on the Spark's CPU in the `speech` service ([speaches](https://speaches.ai):
faster-whisper `small` to transcribe, Kokoro-82M to speak; about 2 GB RAM, no GPU memory). Only
api reaches it. The models download once, at its first start.

- **AnythingLLM** reads replies aloud with it (the speaker button, or auto-play in Settings >
  Voice & Speech), in the Director's voice `af_heart`. Its microphone uses the browser's own
  speech recognition.
- **`POST /v1/voice/turns`** (multipart `audio`, optional `thread_id`, default `voice`): a spoken
  message in, the Director's spoken reply out. The answer is NDJSON, a line per step as it
  happens: `transcript`, then `reply` (with `notices`), then `audio` (base64 mp3), or `error`.
  The turn is an ordinary chat job for the gateway's user, recorded with channel `voice`; the
  voice is the user's `tts_voice` identity fact when set, else `TTS_VOICE`.
- **`POST /v1/audio/transcriptions`** and **`POST /v1/audio/speech`**: OpenAI-compatible, for
  any client (`voice` is a Kokoro voice such as `af_heart` or `am_michael`; `model` is ignored).
- **Limits:** recordings up to `VOICE_MAX_UPLOAD_BYTES` (10 MB); long replies are read in
  sentence pieces. Speech down answers 503. AnythingLLM's read-aloud counts against the owner's
  rate bucket (120 requests a minute), which is ample for one reply at a time.

## Running on the Spark

On the Mac the desk runs for development. On the DGX Spark it runs full time: the whole stack
runs in containers behind one gateway, reachable only over the tailnet.

Before the first deploy, see that:

- the Spark runs Docker Engine 28 or newer (the gateway's healthcheck mounts an image volume);
- the gpt-oss-120b weights are in the Spark's `~/.cache/huggingface` and about 80 GiB of its
  memory is free for the `vllm` service;
- `DB_PASSWORD` and `BROKER_PASSWORD` are URL-safe (letters, digits, `-`, `_`), since they go
  into connection URLs;
- `~/lauretta-stocks` on the Spark is a clone of this repo with its own `.env`, and ssh with a
  key works (the recipes never prompt for a password).

```bash
just deploy             # from the Mac: git pull on the Spark, build natively, migrate, start the stack
just deploy staging     # the same for staging: deploy staging first, main once the phase is reviewed
just ps                 # container status and health
just logs worker        # follow the worker's logs (omit the name for every service)
just backup             # a database dump now, into backups/ on the Spark
```

- **The gateway:** AgentGateway (`services/gateway/config.yaml`). `/v1` and everything under it need
  `Authorization: Bearer` with `GATEWAY_API_KEY` (the owner) or `ANYTHINGLLM_API_KEY`, and so does
  `/mcp` (the owner's key only); `/healthz`
  is open; every other path goes to AnythingLLM, which keeps its own login. It names the user in
  `X-Lauretta-User` (see [Users and isolation](#users-and-isolation)), strips the key and any
  claimed identity (including Tailscale's and forwarding headers), rate limits per user, and
  never buffers a response, so streams and WebSockets arrive as they are written (it reads
  request bodies on `/v1` to find the model). On `/` (AnythingLLM) only, bodies over 100 MiB are
  refused. It alone holds the provider keys, and its internal `llm` listener needs
  `LLM_INTERNAL_KEY`, which the worker holds.
- **The tailnet:** the desk lives at `https://lauretta.tailae2b1.ts.net`. The `tailscale`
  container joins the tailnet as `lauretta-host` (`tag:lauretta`) and hosts the Tailscale Service
  `svc:lauretta`, with a real certificate, straight to the gateway. There is nothing to expose by
  hand: `just deploy` brings it up. Only the owner and the investor can reach it, by tailnet
  policy; Funnel is off. The Spark's `.env` needs `TS_OAUTH_SECRET` (the OAuth client secret,
  copied from the owner's Mac at deploy). The service withdraws when the container stops and
  returns about 20 seconds after it starts. If the `tsstate` volume is ever wiped, delete the old,
  offline `lauretta-host` device in the admin console.
  - **Prerequisites on the tailnet** (all done): the Service `svc:lauretta` defined with
    `tcp:443`, `autoApprovers` for `tag:lauretta`, and HTTPS certificates enabled. The container
    advertises the Service itself on every start and is healthy only once it has (#45).
  - `services/tailscale/serve.json` names the MagicDNS suffix `tailae2b1.ts.net`; renaming the
    tailnet means editing it.
  - After the first login the node lives in `tsstate`, so `TS_OAUTH_SECRET` is only needed again
    if that volume is lost. It stays in the Spark's `.env` (compose requires it), readable with
    `docker inspect`; it is scoped to `auth_keys` for `tag:lauretta` alone.
- **Model:** the worker asks the gateway's internal `llm` port for `gpt-oss-120b`, which the
  `vllm` service serves on the Spark's GPU. vLLM sits on the private `llm` network with the
  gateway alone and reads `SPARK_VLLM_API_KEY` from a secret file. The weights must already be in
  the Spark's `~/.cache/huggingface` (it never downloads them). It takes about 9 minutes to load,
  so a `just deploy` that creates or recreates `vllm` (the first one, or a change to its image or
  flags) waits that long before it returns, and gives up after 20 minutes; the rest of the stack
  is up meanwhile, and model calls fail until `vllm` is healthy. It restarts unless stopped, so a
  load that keeps failing reloads the weights each time: stop it with `docker compose stop vllm`.
  Its flags are a measured memory budget shared with the Spark's other workloads (see the
  comments in `docker-compose.yaml`), so two engines never fit:
  `just deploy` refuses while the hand-started `vllm-gpt-oss-120b` container still runs.
- **Backups:** the `backup` service dumps the database and tars AnythingLLM's storage when it
  starts and at 03:00 UTC into `backups/`, keeps the newest `BACKUP_KEEP` of each, and turns
  unhealthy after 26 hours without either. Restore with `pg_restore`, and untar the storage into
  an empty `anythingllm` volume while AnythingLLM is stopped. The tars hold AnythingLLM's accounts
  and keys, so keep `backups/` private.
- **Restarts:** the gateway starts once AnythingLLM has started (it never waits for its health),
  but recreating `anythingllm` restarts the gateway, which cuts any stream in flight. Deploy with
  `docker compose up -d` for all services (as `just deploy` does); if `anythingllm` is ever
  recreated alone, restart the gateway after it, or the gateway keeps its old address.
- **Gotchas:** the gateway's `requestTimeout` bounds only the time to response headers, not a
  stream; `csrf` is not authentication; and the gateway expands `${...}` even in config comments.

| Port | Bound to | Serves |
|---|---|---|
| 443 on `lauretta.tailae2b1.ts.net` | tailnet only (`svc:lauretta`) | HTTPS to the gateway |
| 18400, 3000 | compose networks `edge`, `app`, `models`, `web` and `llm` | gateway ingress and `llm` |
| 3001 | compose network `web` only | anythingllm |
| 8000 | `app` (the gateway), `api-data` (db, broker), `speech`; refuses requests without the gateway secret | api |
| 5432, 6379 | `api-data` (api), `worker-data` (worker); 5432 also `dump` (backup) | db, broker |
| 8000 | compose network `llm` only | vllm |

## Users and isolation

The owner (`mat`) and Max (`max`) chat with the same Director, and neither can reach the other's
memories, holdings, theses, conversations, jobs or events. Who is asking is decided by the
infrastructure, never by the model or by anything in a request body, and every layer enforces it
on its own:

| Layer | What holds |
|---|---|
| gateway | Names the user in `X-Lauretta-User` and removes any client copy. The owner's key is always `mat`. AnythingLLM's key names the user from the model its workspace chats with (`lauretta-mat`, `lauretta-max`) and may only list models and chat; any other model names nobody. |
| networks, api edge | api shares networks with the gateway, the database, the broker and speech, so networks alone are not trusted: the gateway adds `X-Lauretta-Gateway` with a secret only it and api hold, and api refuses every request without it (`api/edge.py`; `/healthz` stays open). |
| api | Acts only for a user in `ALLOWED_USERS` (else 401). Another user's job, status or events is 404. A chat model must be the caller's own (`lauretta-<user>`, else 404). Threads are keyed `{user}:{thread}` on the server. |
| queue, worker | A job carries its user; locks, checkpoints and signals are keyed by it. |
| graphs | The user is LangGraph runtime context (`graph/ctx.py`). Tools read it through `ToolRuntime`, which is not in any schema the model sees, so the model can neither read nor set it. |
| Postgres | api and worker connect as `lauretta_app` (no superuser, no BYPASSRLS). Forced row-level security on `facts`, `holdings`, `theses`, `threads` and `thread_aliases` shows each transaction only the rows of its `app.user_id`; a query outside a user's scope sees nothing. LangGraph's checkpoint tables are created by a one-shot deploy step, the compose `migrate` service, as `lauretta_migrator` (no superuser, no rights on those five tables); the long-running api and worker hold neither that role nor the owner's password, and the worker only checks the tables are current. |

Tests: `just test` covers the api, queue, worker and graphs (including prompt injection as Max);
`just test-db` runs the row-level security tests against a throwaway database (on the Spark).

**Passwords:** `DB_APP_PASSWORD` and `DB_MIGRATOR_PASSWORD` set the roles' passwords once, when
the db volume is created. To rotate one, change it in `.env` and also run, as the owner,
`ALTER ROLE lauretta_app PASSWORD '...'` (or `lauretta_migrator`), then restart api and worker.

**Deploying this change** (the schema changed, so the database is recreated; the owner's data is
carried over): on the Spark, check out the new code, add `DB_APP_PASSWORD`,
`DB_MIGRATOR_PASSWORD` and `ANYTHINGLLM_API_KEY` to `.env` (URL-safe), remove `USER_ID`, rotate
`GATEWAY_API_KEY`, and run `sh services/db/reset-and-restore.sh`. It stops api, worker and
AnythingLLM before it dumps, refuses if any row belongs to someone other than `mat`, recreates only
the database (vllm keeps running), restores table by table (`--exit-on-error`, threads before
aliases), moves conversations to `mat:<thread>`, checks every count against the dump, and only
then starts the stack. The dump stays in `backups/pre-isolation-*.dump`.

**Setting up the people in AnythingLLM** (once per person, by an admin): create a workspace
(e.g. "Mat", "Max"), set its chat model to `lauretta-<user>` (workspace settings, or the
developer API `POST /api/v1/workspace/{slug}/update` with `{"chatProvider": "generic-openai",
"chatModel": "lauretta-max"}`), and give only that person access to it (the workspace's members,
or `POST /api/v1/admin/workspaces/{slug}/manage-users` with `{"userIds": [<id>], "reset": true}`).
A chat anywhere else uses the default model `lauretta`, which the desk refuses. Create no embed
widgets on these workspaces.

**Adding a user** touches five places:

1. their id in `ALLOWED_USERS` (`.env`, or the compose default);
2. the gateway's `ingress-api` user map (`X-Lauretta-User`): `"lauretta-<id>": "<id>"`;
3. the gateway's authorization rule, which lists the models AnythingLLM may chat with;
4. the gateway's rate-limit buckets (a `conditional` entry for their model);
5. an AnythingLLM workspace with chat model `lauretta-<id>`, shared with them alone.

**What this does not cover:**

- **AnythingLLM itself.** Its admins can open any workspace, including another person's, and chat
  there as that person. Both accounts are admins today; once each phone is paired, demote both to
  **Default** (a paired device stays linked to its user), after checking that a Default user
  cannot change a workspace's model.
- **AnythingLLM's developer API key** reaches every workspace over the tailnet, so it can chat as
  either person. Keep it in `.claude/secrets/` and revoke it when setup is done.
- **Embed widgets** chat into a workspace without any login: one on Mat's workspace would let
  anyone who finds it chat as mat. Do not create any.
- **Agent mode** uses the workspace's agent model, which is `lauretta` by default and refused;
  setting it to `lauretta-<user>` would act as that user too.
- Whoever holds `ANYTHINGLLM_API_KEY` or AnythingLLM's storage can act as either person.
- **db and broker share a network with api** (they must reach each other), so a compromised db
  or broker container could send api a forged user header. api and worker hold `lauretta_app`
  and can scope as any user: row-level security guards against bugs and prompt injection, not a
  compromised app container.
- **Checkpoint tables** (conversation history) have no user column and no row-level security;
  they are kept apart by the server's `{user}:{thread}` keys, and no route reads them.
- **Local development** connects as the owner, a superuser, so row-level security does not apply
  there; `just test-db` checks the policies.

The stack publishes no host ports at all, vLLM included, so the Spark's firewall needs no rule
for it. For local development, `just up` still starts only the database, on loopback `DB_PORT`.
