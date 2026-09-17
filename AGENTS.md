# AGENTS.md

A proof of concept for a friend: a research assistant for one private investor. It learns how
they invest, keeps their holdings, and runs a three-agent research team on a stock. It never
trades; it suggests. The background and open requirements questions are in `.cache/PLAN.md` (local only, not committed).

Run `just --list` for every command.

## How it works

```
chat (LangGraph, checkpointed in Postgres)
  context -> agent <-> tools -> notice  memory, holdings, snapshot, get_thesis, research_stock,
                                        set_identity, set_user_details, propose_soul_change
                                                                                  |
research pipeline (LangGraph)                                                     v
  load_context -> analyst -> checker --revise (max PIPELINE_MAX_REVISIONS)--> analyst
                               \--approve / out of redrafts--> advisor -> save (theses table)
```

- **Roles** (`agent/src/graph/role.py`): each is a model node + ToolNode loop that ends when
  its submit tool writes a validated result (`graph/outputs.py`). No submit is a hard error.
- **Analyst** writes the stock story: business, driver, market gap, catalyst (dated), falsifier,
  risks, a sourced data snapshot, data gaps.
- **Checker** re-pulls the figures with the same tools and approves or sends it back with
  required changes.
- **Advisor** reads portfolio weights and memories; suggests buy/add/hold/trim/sell/watch/avoid
  with a target weight, or refuses to size while the core profile is unknown.
- **Assistant** (chat) onboards the investor into memory until the core topics
  (`memory/topics.py`) are known, then relays the team's results.
- **Stage** (`bootstrap`/`onboard`/`ready`) is decided in code from what facts hold, never by
  the model: bootstrap until both names are known, onboard until the core topics are known.
- **Persona** (chat assistant only): `<rules>` (code, `persona/rules.py`) then `<soul>`,
  `<identity>`, `<user>`, `<signals>`. The soul changes only when the investor replies
  `approve soul <id>`, which code applies in the context step; the advisor sees `<user>` only.

## Layout

- `agent/src/graph/prompts/`: one system prompt per agent: a `_HEAD`, then data blocks
  (`<investor>`, `<holdings>`, `<unknown>`, `<draft>`, `<review>`), then the stage instruction.
- `agent/src/tools/`: one `build_*` factory per tool; argument schemas in `tools/models.py`.
- `agent/src/data/`: `sec.py` + `xbrl.py` (SEC EDGAR, free, needs `SEC_USER_AGENT`),
  `market.py` (yfinance, free, unofficial).
- `agent/src/persona/`: rules and default soul as constants, prompt blocks, soul approval.
- `agent/src/db/`: pool, checkpointer, and `queries/` for facts (memories, profile, identity,
  signals, soul), holdings and theses. Signals are written by code (`facts.record_signals`).
  Schema is `db/init/00-schema.sql` (applied when the volume is first created).
- `agent/src/api/`: FastAPI (`src.api.app:app`). Queues jobs and reads results; never runs a
  graph. `POST /v1/jobs` (`?wait=`), `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/events` (SSE),
  `/v1/theses/{ticker}`, `/v1/holdings`, `/healthz`. `api/openai/`: `/v1/models` and
  `/v1/chat/completions` (OpenAI-compatible, streamed), a thin adapter over the same jobs; the
  user comes from `deps.current_user`; threads are owned in `threads` and found again through
  `thread_aliases` (hashes of prompt and answer pairs the client resends).
- `agent/src/queue/`: Valkey Streams: `jobs` (group `workers`, reclaim, `jobs:dead`), per-job
  status hash and `job:{id}:events` stream, per-thread lock. Event models in `queue/models.py`.
- `agent/src/worker/`: `python -m src.worker` runs jobs through `open_app`; `stream.py` maps
  LangGraph stream parts to events. Nodes report progress, notices and retries through
  `graph/emit.py` (a no-op under `ainvoke`, so the CLI is unchanged).
- `agent/src/memory/`: fastembed embeddings (local CPU, 384 dims) for pgvector search.
- `agent/Dockerfile`, `docker-compose.yaml`, `ops/`: the Spark stack (gateway, api, worker, broker,
  db, anythingllm, backup, tailscale). The gateway sends `/v1/*` and `/healthz` to api and every
  other path to AnythingLLM, the web and Android client (`ops/gateway/config.yaml`). The
  tailscale container hosts the Service `svc:lauretta` (`ops/tailscale/`). `docker-compose.dev.yaml` is the local db only, used by `just up`.

## MCP servers (`.mcp.json`)

- `langgraph-docs`, `context7`: current LangGraph/LangChain and library docs. Check them before
  changing graph, tool or checkpointer code; do not rely on memory of these APIs.
- `postgres`: read-only (restricted) access to the local db on :5433 while `just up` runs. Use it
  to inspect facts, holdings, theses and checkpoints.
- `fetch`: read a web page, for example an SEC filing linked in a thesis.

## Rules

- Fail hard; never hide a failure. A data source that cannot be read is reported to the model
  as `available: false` with a reason, never replaced with a guess.
- Every figure an agent states must come from a tool result in that run.
- Nothing places trades or touches a brokerage.
- Prefer free data sources; a paid one needs the owner's approval first.
- Keep Python files under 150 lines where it is logical.
- Changing the schema means `just down clean=true` then `just up` (POC, no migrations).
- Never read or commit `.env`; add new settings to `.env.example` and `src/settings.py`.

## Software development lifecycle

- **Planning:** turn requirements into GitHub issues, one per feature, written as (1) problem,
  (2) objective and outcomes, (3) task list. Each issue is scoped for one agent; issues may run
  in parallel only when their responsibilities do not overlap.
- **Execution:** give each agent a fixed scope and every detail it needs. Each agent works in its
  own git worktree under `.claude/worktrees/`, named for what it is working on. Remove the
  worktree and stop the agent once its PR is merged.
- **Branches:** branch off `staging`, one feature per branch, merged into `staging` by pull
  request. `main` only receives `staging` once every issue in a phase is merged, reviewed and
  deployed successfully.
- **Review:** every pull request gets a full code review, by a separate reviewer from the author,
  before it merges. Merging `staging` into `main` needs a full review of the phase.
- **Testing:** write unit tests that match the issue's outcomes. `just test` must pass before
  committing and before merging.
- **Issue board:** [Lauretta-stocks project](https://github.com/users/SuperElectron/projects/6),
  linked to this repo. Move each issue through `Todo` (planning), `Ready` (approved, an agent
  can take it), `In progress` (an agent is on it and opens a PR into `staging` when done), `In review`
  (PR open or merged into `staging`) and `Done` (merged into `main`).
- Never push or force-push without the owner's say-so.
