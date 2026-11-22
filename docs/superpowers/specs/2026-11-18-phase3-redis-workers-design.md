# TaskFlow Phase 3 Design: Redis Integration + Synchronous Workers

**Date:** 2026-11-18
**Status:** Approved 2026-11-18 — implemented (PR #4); follow-up hardening tracked in issue #6
**Author:** Coding agent

## 1. Intent and why

TaskFlow currently accepts jobs via API and persists them to PostgreSQL, but nothing executes them. Phase 3 introduces Redis as the job queue broker and synchronous Python workers that dequeue and execute registered handlers. This is the first step toward the project's core purpose: distributed background job processing.

## 2. Goals, non-goals, anti-goals

### Goals
- Jobs submitted via `POST /jobs` are enqueued to Redis and executed by background workers.
- Worker execution updates `Job` status (`pending → running → completed/failed`), `result`, `error`, `started_at`, `completed_at`.
- Only registered handlers can execute; arbitrary user-supplied code is never run.
- API, database, queue, and worker responsibilities remain separated.
- Workers run as separate Python processes (synchronous, no concurrency yet).
- Idempotent processing: duplicate queue entries cannot double-execute a job.

### Non-goals (Phase 3)
- Concurrency, async workers, retries with exponential backoff, dead-letter queues (Phase 4).
- Worker health monitoring, metrics, tracing (Phase 4).
- Stale `running` job recovery (Phase 4 — see Known limitations).
- CLI submission (future phase).

### Anti-goals (would make this a failure even if it technically works)
- A job stranded in `pending` forever because Redis was down at submission time.
- A job stranded in `running` because a handler's return value could not be stored.
- A worker executing an unregistered handler.
- Two workers processing the same job simultaneously.
- Redis connection details leaking into API route or worker business logic.

## 3. Constraints

- All credentials and connection strings via environment variables (`DATABASE_URL`, `REDIS_URL`). `.env` never committed.
- Registered job handlers only — never execute arbitrary user-supplied Python or shell commands.
- Minimal initial implementation. Do not build everything at once.
- Add basic tests as each component is implemented.
- Keep API, database, queue, and worker responsibilities separated.
- The default `pytest` run must stay green on a machine with neither Redis nor PostgreSQL installed.
- Order per `agents.md`: job model → database → migrations → job submission/retrieval → Redis → workers.
- Do not push additional changes without showing me what was implemented and letting me review them.

## 4. Approaches considered

### Approach A: Redis Lists + API enqueues + handler registry (selected)
API creates `Job` (status=`pending`), pushes job ID to Redis list. Worker `BLPOP`s the list, fetches the job, sets `running`, executes the registered handler, sets terminal state. Handler registry lives in `app/jobs/registry.py`; built-in handlers register themselves from `app/jobs/handlers/`.

**Trade-offs:** Minimal Redis integration that actually uses Redis as a queue. Clear separation of concerns. Slightly more moving parts than DB polling, but that's the point of Phase 3.

### Approach B: Redis Streams + worker polls DB (rejected)
API writes to DB only; worker polls DB and uses Redis Streams for notification. Over-engineered for Phase 3 — consumer groups and acknowledgement add complexity without benefit yet.

### Approach C: Redis Lists + worker polls DB, no API enqueue (rejected)
API writes to DB only; worker polls for `pending` jobs. Redis is unused as a queue — defeats the purpose of introducing it.

### Approach D: Redis Lists + best-effort enqueue + startup sweep (rejected for Redis-down handling)
If Redis is down at submission, the job stays `pending` and a startup sweep re-enqueues it later. This leaves jobs stranded until the next worker restart — contradicts the "never leave a job hanging" constraint.

### Selected Redis-down handling
Commit the row, push to Redis, on push failure mark the job `failed` with `error` set and return HTTP 503. Nothing is silently stranded. Best-effort + startup sweep deferred to Phase 4.

## 5. Design decisions (as agreed)

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Handler registry | `app/jobs/registry.py` | Maps handler name → handler function. Imported by API (validation) and workers (execution). |
| Built-in handlers | `app/jobs/handlers/` | Register themselves on import. Demo handlers: `echo`, `add_numbers`. Kept under `app/jobs/` rather than `app/workers/` so the API process can load the registry without importing the worker package. |
| Registration bootstrap | `app/jobs/handlers/__init__.py` | Imports every handler module. Imported at startup by `app/main.py` and `app/workers/__main__.py` (see §5.1). |
| Queue client | `app/queue/client.py` | Thin wrapper around the Redis list `taskflow:jobs`: `enqueue(job_id)`, `dequeue(timeout)`. Injected as `get_queue()`. |
| Queue fake (tests) | `tests/` | In-memory fake overriding `get_queue()`. |
| Worker entry | `app/workers/__main__.py` | `python -m app.workers` — process entry: signal handling, dequeue loop, per-job session. |
| Worker logic | `app/workers/worker.py` | Dequeue, fetch job, claim `pending → running`, execute handler, set terminal state. |
| Job model changes | None | `result`, `error`, `started_at`, `completed_at` already exist. |
| Migration changes | None | `0001_create_jobs_table` already created all needed columns. |
| Dependency changes | None | `redis>=5.0.0` already in `pyproject.toml`. |

### 5.1 Handler registration bootstrap

The registry is process-local and populated by import side effects, so both
processes must import it explicitly:

- `app/jobs/handlers/__init__.py` imports every handler module (`echo`, `add_numbers`).
- `app/main.py` imports `app.jobs.handlers` at module scope, so the API process can validate `handler` on `POST /jobs`.
- `app/workers/__main__.py` imports `app.jobs.handlers` at module scope, so the worker process can resolve names at execution time.

Without these imports the registry is empty and every submission is rejected with 422. A test asserts that importing the app exposes at least the demo handlers, so this cannot regress silently.

### Handler contract

- Signature: `handler(payload: dict[str, Any]) -> dict[str, Any] | None`. `payload` is always a dict — the column is non-nullable with a `{}` default — so it is never `None`.
- Returns a JSON-serialisable `dict` → stored as `Job.result`, status `completed`.
- Returns `None` → `Job.result = None`, status `completed`.
- Raises any exception → `Job.error` set, status `failed`.
- Returns anything other than `dict | None`, or a dict that is not JSON-serialisable → status `failed` with a contract error.
- The worker validates serialisability (`json.dumps(result)`) **before** writing `completed`, so a bad return value cannot strand a job in `running`.

Demo handlers:

| Handler | Payload | Result |
|---------|---------|--------|
| `echo` | any JSON object | the payload, unchanged |
| `add_numbers` | `{"a": <number>, "b": <number>}` | `{"sum": <number>}` |

`add_numbers` raises `ValueError` when `a`/`b` are missing or non-numeric, which exercises the failure path.

### Job lifecycle transitions
```
pending → running → completed
pending → running → failed
```

### Claiming a job (idempotency)

The transition to `running` is a single conditional statement, not a
read-then-write:

```sql
UPDATE jobs SET status = 'running', started_at = now()
WHERE id = :id AND status = 'pending'
```

If `rowcount == 0`, another worker already claimed the job (or it is already
terminal) and this worker logs and moves on. Duplicate queue entries therefore
cannot double-execute, even if Phase 4 adds more workers, and there is no
check-then-act race.

### Unknown handler at execution time
If a job with an unregistered handler is executed (typo submitted before registry validation existed, or row inserted directly into DB), the worker marks it `failed` with `error` set, never left in `pending`.

### Worker loop behaviour

- `dequeue(timeout=5)` → `BLPOP taskflow:jobs 5`. The timeout keeps the loop responsive to shutdown signals; an empty result is normal, not an error.
- Malformed queue entry (not a parseable UUID) → log a warning and discard; there is no job to fail.
- Job ID that no longer exists in the database → log a warning and discard.
- `SIGINT`/`SIGTERM` set a stop flag; the current job finishes, then the process exits. A normal shutdown never abandons a job mid-flight.
- One `Session` per job, opened and closed around it, so a failed job cannot poison the next one (`pool_pre_ping` already handles stale connections).
- Errors are persisted as `f"{type(exc).__name__}: {exc}"`, truncated to 2000 characters. The full traceback goes to the worker log only, never to the API response.

### Redis-down on `POST /jobs`
1. Commit `Job` row with status `pending`.
2. Push job ID (as a string) to the Redis list `taskflow:jobs`.
3. If push fails: mark job `failed` with `error` describing the queue failure (rollback is not applicable — the row is already committed) and return HTTP 503.
4. The job is not lost — it exists in the DB with a terminal state and an error message.

### Known Phase 3 limitations

- A worker that dies mid-job (OOM, `kill -9`, host loss) leaves the job in `running` forever. Detection (heartbeat / stale sweep) is Phase 4 alongside retries. Recorded here so it is not later mistaken for an unnoticed bug.
- If Redis is down *and* the follow-up "mark job failed" write also fails (database unreachable), the job remains `pending`. The API logs this loudly (including the job id) and returns 503; reconciliation arrives with the Phase 4 sweep.
- There is a crash window between the first `db.commit()` and `queue.enqueue()`: if the API process dies in between, the row stays `pending` with no queue entry and nothing re-enqueues it. The queue is the only trigger; only the Phase 4 reconciler can recover these rows.
- Job payloads are capped at `MAX_PAYLOAD_BYTES` (64 KiB of compact JSON) at the API boundary. The cap bounds memory and storage cost per submission; it is not a licence to store large documents.
- **No authentication or authorisation.** Anyone who can reach the API can submit work and read any job's `payload`/`result`; the job UUID is effectively a bearer token. Payloads and results are not a secret store. Acceptable for the current local/learning phase, and must be written down rather than implied.
- **No tenancy.** `Job` has no owner/`tenant_id`, `GET /jobs/{id}` is unscoped, and all callers share the single `taskflow:jobs` Redis key. This is an explicit assumption for Phase 3, not an oversight: adding auth later without tenant scoping would turn the current design into a cross-tenant data leak.

### Testing strategy

- The default `pytest` run passes with no Redis and no PostgreSQL installed.
- API and worker tests inject an in-memory queue fake through `get_queue()`, mirroring the existing suite's `get_db` override.
- Real-Redis tests (enqueue/dequeue round-trip) sit behind a marker and are skipped unless a Redis URL is supplied explicitly, e.g. `pytest -m integration` with `TASKFLOW_TEST_REDIS_URL` set. They are excluded from the default run because Docker and `redis-server` are unavailable on this machine.

### Acceptance tests for Phase 3

1. `POST /jobs` with a registered handler → 201, row `pending`, exactly one queue entry.
2. `POST /jobs` with an unregistered handler → 422 naming the valid handlers, no row, no queue entry.
3. `POST /jobs` when `enqueue` raises → 503, and the job row ends `failed` with `error` set.
4. Worker executes `echo` → `completed`, `result` equals the payload, `started_at` and `completed_at` set.
5. Worker executes `add_numbers` → `completed`, `result == {"sum": 3}`.
6. Handler raising → `failed`, `error` populated, `result is None`.
7. Handler returning a non-dict → `failed` with a contract error, not `running`.
8. Handler returning a non-serialisable dict → `failed` with a contract error.
9. Unregistered handler name already in the DB → `failed`, never left `pending`.
10. Duplicate queue entry for the same ID → executed once, second entry skipped.
11. Importing the app populates the registry (guards the §5.1 bootstrap).
12. Malformed queue entry → discarded, worker keeps running.

## 6. What's left to the builder

- Implement `app/jobs/registry.py` with the `register_handler(name)` decorator and `get_handler(name)` / `registered_handlers()` lookup.
- Implement `app/jobs/handlers/` (`__init__.py`, `echo.py`, `add_numbers.py`) with the demo payload contracts above.
- Implement `app/queue/client.py` Redis-backed client (`enqueue`, `dequeue`) and the `get_queue()` dependency.
- Implement `app/workers/` package (`__main__.py`, `worker.py`): signal handling, conditional claim, JSON validation before `completed`, per-job session.
- Wire the §5.1 imports into `app/main.py` and `app/workers/__main__.py`.
- Update `POST /jobs` to validate `handler` against the registry (422) and enqueue after DB commit, with the 503 failure path.
- Update `infra/docker-compose.yml` worker command from `python -m app.worker` to `python -m app.workers`.
- Implement the acceptance tests above; convert the existing API tests that use `send_email` / `process_image` to `echo` / `add_numbers`.
- Update `agents.md` Phase 3 section as components land.
- Update `README.md` with worker and queue documentation.

## 7. Approval

Approved by the project owner on **2026-11-18**, and implemented in PR #4 (`135b765`). The open follow-ups from the post-merge review live in issue #6; this section stays as the record of the approval date.

---

**Builder check (self-review):** Every component has a concrete location and the dependency direction is one-way (API → `app.jobs.registry`, workers → `app.jobs.registry`; neither imports the other). Registration is bootstrapped explicitly in both entry points and guarded by a test. The handler contract is typed and its bad-return path is verified before the job leaves `running`. Claiming is a single conditional UPDATE. Failure modes are enumerated: Redis down at submission, unknown handler, malformed queue entry, non-serialisable result, worker crash (deferred, documented). Default tests need no external services; real-Redis tests are opt-in. No migration and no new dependency is required.
