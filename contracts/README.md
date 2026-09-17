# Contracts

What crosses the boundary between `services/api` and `services/agent` (the worker). Each service
mirrors these in its own code and never imports the other; its tests load the fixtures here, so
both mirrors keep the same shape.

| File | What it pins | Mirrored by |
|---|---|---|
| `queue_keys.v1.json` | Valkey stream and group names, the job entry's payload field, the `job:{id}` status hash fields and statuses, and key vectors (`job`, `events`, `thread`, `thread_lock`, `thread_job`, `request`) | `api`, `agent` |
| `job.v1.json` | The job payload on the `jobs` stream: valid jobs per kind and channel, and invalid ones that must be refused | `api`, `agent` |
| `job_events.v1.json` | One example of each event on `job:{id}:events` (`type` plus its JSON `data`), which are terminal, and the Director's default name for progress events without one | `api`, `agent` |

Rules:
- A job's `user` is set by the API from the gateway's header, never from a request body.
- `timeout` is sent by the API alone, never stored on the stream.
- `error` carries a code and wording only, never exception text.
- Changing a contract means a new version file, or both services changed in the same PR.
