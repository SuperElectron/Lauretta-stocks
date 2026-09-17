# AGENTS.md

A proof of concept for a friend: a research assistant for one private investor. It learns how
they invest, keeps their holdings, and runs a three-agent research team on a stock. It never
trades; it suggests. The background and open requirements questions are in `.cache/PLAN.md` (local only, not committed).

Run `just --list` for every command.

## How it works

```
chat (LangGraph, checkpointed in Postgres)
  context -> agent <-> tools -> notice  memory, holdings, snapshot, get_thesis, research_stock,
                                        set_identity, set_user_details, skip_setup_step,
                                        propose_soul_change
                                                                                  |
research pipeline (LangGraph)                                                     v
  load_context -> analyst -> checker --revise (max PIPELINE_MAX_REVISIONS)--> analyst
                               \--approve / out of redrafts--> advisor -> save (theses table)
```

- **Roles** (`services/agent/src/graph/role.py`): each is a model node + ToolNode loop that ends
  when its submit tool writes a validated result (`graph/outputs.py`). No submit is a hard error.
- **Analyst** writes the stock story: business, driver, market gap, catalyst (dated), falsifier,
  risks, a sourced data snapshot, data gaps.
- **Checker** (the `checker` node) re-pulls the figures with the same tools and approves or sends
  it back with required changes.
- **Strategist** (the `advisor` node) reads portfolio weights and memories; suggests
  buy/add/hold/trim/sell/watch/avoid with a target weight, or refuses to size while the core
  profile is unknown.
- **The Director** (the chat assistant) guides the investor through setup, then relays the
  team's results.
- **Setup** (`graph/setup.py`, wording in `prompts/setup.py`): the context node computes the
  steps from memory every turn (`investor_name`, `team_names` optional, `core_profile` from
  `memory/topics.py`, `holdings` optional) into `setup` in `ChatState`, and renders a `<setup>`
  checklist with the one next step. `skip_setup_step` stores a `setup_team_names` or
  `setup_holdings` fact (value `skipped`, never returned by memory search) when the investor
  declines an optional step, so it is never asked again. Persona facts, memories and holdings
  are read once per turn or run (`context.load_known`); the pipeline builds the same setup from
  them for the Strategist's unknown core topics.
- **Stage** (`setup`/`ready`) is decided in code from `setup`, never by the model: `setup` while
  any step is still to do.
- **Persona** (chat assistant only): `<rules>` (code, `prompts/rules.py`) then `<soul>`,
  `<identity>`, `<user>`, `<signals>`. The soul changes only when the investor replies
  `approve soul <id>`, which code applies in the context step; the advisor sees `<user>` only.
- **Names**: every agent's name (Director, Analyst, Checker, Strategist) is an identity fact
  (`bot_name`, `analyst_name`, `checker_name`, `strategist_name`) with its default in
  `prompts/identity.py`; `set_identity` renames them. The pipeline loads the names once per run,
  tells each role its name, and sends it on every progress event (`name`, optional).

## Layout

Every service has its own folder under `services/` (`agent`, `db`, `gateway`, `tailscale`,
`backup`); the repo root keeps the compose files, `justfile`, docs, `reports/` and `backups/`.
Paths below are relative to `services/`.

- `agent/src/prompts/`: all prompts and user-facing wording live here, and nowhere else: rules,
  default soul and desk lines, identity defaults, each agent's system prompt (`assistant`,
  `analyst`, `checker`, `strategist`), block empty states, progress labels, client notes, error
  text (`errors`), tool notes (`tools`), fact sentences (`facts`), the setup checklist (`setup`)
  and the report. It imports nothing.
  Templates use `str.format` fields; `tests/unit/test_prompts.py` checks their fields and fails
  on wording found elsewhere (explicit `file:symbol` allowlist, each with a reason). Tool
  descriptions stay as docstrings and `Field` descriptions on the tools.
- `agent/src/graph/render.py`: stitches each system prompt from that wording: a head, then data
  blocks (`<investor>`, `<holdings>`, `<setup>`, `<unknown>`, `<draft>`, `<review>`), then the
  stage.
- `agent/src/tools/`: one `build_*` factory per tool; argument schemas in `tools/models.py`.
- `agent/src/data/`: `sec.py` + `xbrl.py` (SEC EDGAR, free, needs `SEC_USER_AGENT`),
  `market.py` (yfinance, free, unofficial).
- `agent/src/persona/`: persona prompt blocks, the soul cap check, and soul approval.
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
- `agent/Dockerfile`, `db/`, `gateway/`, `tailscale/`, `backup/` and the root `docker-compose.yaml`:
  the Spark stack (gateway, api, worker, broker, db, anythingllm, vllm, backup, tailscale). The
  gateway sends `/v1/*` and `/healthz` to api and every other path to AnythingLLM, the web and
  Android client (`gateway/config.yaml`). Its internal `llm` listener, which api and worker call,
  forwards to the `vllm` service (gpt-oss-120b on the Spark's GPU) on the private `llm` network. The tailscale container hosts the Service `svc:lauretta`
  (`tailscale/`). AnythingLLM is an image with settings in compose; it has no folder.
  `docker-compose.dev.yaml` is the local db only, used by `just up`.

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
