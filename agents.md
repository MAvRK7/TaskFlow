# agents.md — TaskFlow AI Agent Working Guide

This file is written for **me (the coding agent)** to understand the TaskFlow project, how the repo is set up, how to work on it, and what conventions to follow. Keep it up to date as the project evolves.

---

## 1. Project identity

- **Name:** TaskFlow
- **Repo:** `https://github.com/MAvRK7/TaskFlow.git` (pushed, authenticated as `MAvRK7`)
- **Working directory:** `/Users/satvikraghav/coding/TaskFlow`
- **Description:** Distributed background job processing platform built with **FastAPI**, **PostgreSQL**, **Redis**, and **Python workers**. Applications, CLI users, and AI agents submit async jobs, track execution status, and retrieve results through a unified API.
- **Core concepts explored:** job queues, concurrency, retries, fault tolerance, scalability, observability.
- **License:** Apache-2.0 (see `LICENSE`).

## 2. Repo state (as of setup)

The upstream repo originally contained only an **"Initial commit"** with two files:
- `.gitignore` (Python-focused)
- `LICENSE` (Apache-2.0)

**Scaffold applied:** The folder template has been applied and pushed to `origin/main`.

**Phase 1 complete (committed and pushed to `origin/main`):**
- Job model (`Job`, `JobStatus`) in `backend/app/jobs/models.py`
- Database connection (`Base`, `get_engine`, `get_session_local`, `get_db`) in `backend/app/db/session.py`
- Alembic migrations (`alembic/`, initial migration `0001_create_jobs_table`)
- uv package management (`pyproject.toml`, `uv.lock`)
- `.env.example` (never commit `.env`)
- Tests: 5 tests in `backend/tests/test_job_model.py`, all passing
- Ruff lint/format: all checks passing

**Phase 2 complete (reviewed, committed and pushed to `origin/main`):**
- `POST /jobs` (creates `Job` with status `pending`, 201) in `backend/app/api/routes.py`
- `GET /jobs/{job_id}` (status/result, 404 for unknown id) in `backend/app/api/routes.py`
- Pydantic API contract in `backend/app/jobs/schemas.py` (`JobCreate`, `JobRead`)
- Routes wired into `backend/app/main.py`
- 6 API tests in `backend/tests/test_api.py` (TestClient + in-memory SQLite) — full suite 13 passing
- Review fixes applied: `JobCreate.handler` bounded to `min_length=1, max_length=255` to mirror the DB `String(255)` column (avoids a Postgres-only naked 500); boundary tests added for invalid payload type and oversized handler
- **Conscious deferral:** handler-registry validation is Phase 3 scope (registry doesn't exist yet); documented in `create_job` docstring

Minor polish deferred to a later pass: `JobRead.status` could use the `JobStatus` enum; `created_at`/`updated_at` typed optional though non-null; router `tags=["jobs"]`.

## 3. Tech stack (decisions made)

| Layer | Technology | Decision |
|-------|-----------|----------|
| API | FastAPI (Python 3.13) | REST API for job submission, status, results |
| Job store / state | PostgreSQL (Supabase) | Connection via `DATABASE_URL` env var |
| Job queue / broker | Redis | Connection via `REDIS_URL` env var; Docker locally |
| Workers | Python (synchronous, separate processes) | Modular; concurrency added later |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | `app/db/session.py`, `alembic/` |
| Package manager | uv | `pyproject.toml` + `uv.lock` (committed) |
| Config | Environment variables | `.env.example` template; `.env` never committed |
| Tests | pytest | In-memory SQLite for unit tests |
| Lint/format | Ruff | `ruff check`, `ruff format` |
| CI/CD | GitHub Actions + Dependabot | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/CODEOWNERS` |
| Branch protection | GitHub repo settings | `main` protected; status checks + code owner reviews required |

## 4. CI/CD (GitHub Actions + Dependabot)

**`.github/workflows/ci.yml`** — three jobs:
- **`test`** — `uv sync --locked`, `uv lock --check`, `uv run pytest tests/`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app/`. Runs on push/PR to `main`. All `run:` steps execute from `backend/` via `defaults.run.working-directory`.
- **`integration`** — Same steps, but with Postgres (`postgres:16-alpine`) and Redis (`redis:7-alpine`) service containers provisioned with health checks. Ready for Phase 3 worker tests; current tests still run against in-memory SQLite.
- **Action versions** — `actions/checkout@v7`, `actions/setup-python@v7`, `astral-sh/setup-uv@v7` (bumped via Dependabot PRs #1-#3).

**`.github/dependabot.yml`** — weekly updates:
- `uv` ecosystem at `/backend` (Python deps → `uv.lock`)
- `github-actions` ecosystem at `/` (action versions)

**`.github/CODEOWNERS`** — `@MAvRK7` review required for `/backend/`, `/.github/`, `pyproject.toml`, `uv.lock`, `agents.md`, `README.md`.

**Branch protection on `main`** (GitHub repo settings):
- Required status checks: `CI/test`, `CI/integration` (strict — must be up to date)
- Required PR reviews: 1 approval, code owner review required, stale reviews dismissed
- Force pushes: blocked
- Branch deletion: blocked

## 5. Local environment

Checked on this machine (macOS):

- **Python:** 3.13.13 ✅
- **Git:** configured (user: Satvik Raghav / satvikraghav007@gmail.com) ✅
- **uv:** 0.13.8 ✅ (installed at `~/.local/bin/uv`)
- **Docker:** ❌ not installed
- **PostgreSQL (`psql`):** ❌ not installed
- **Redis (`redis-cli`):** ❌ not installed

Docker is unavailable locally, so Redis runs via Docker in deployment/CI. Database is Supabase PostgreSQL accessed via `DATABASE_URL` env var. Tests use in-memory SQLite so no live DB is required.

Suggested local Redis (Docker not available on this machine — user must provide or install Docker):
```bash
# If Docker becomes available:
docker run -d -p 6379:6379 redis:7-alpine
```

## 5. Folder structure

Canonical tree:

```
taskflow/
├── backend/
│   ├── pyproject.toml        # uv project config + dependencies
│   ├── uv.lock               # locked dependencies (committed)
│   ├── .env.example          # env var template (copy to .env; never commit .env)
│   ├── alembic.ini           # Alembic config
│   ├── alembic/
│   │   ├── env.py            # loads .env, target_metadata = Base.metadata
│   │   └── versions/
│   │       └── 0001_create_jobs_table.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI entrypoint (/health, /)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py     # Settings from environment variables
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   └── session.py    # SQLAlchemy engine, session, Base
│   │   ├── jobs/
│   │   │   ├── __init__.py
│   │   │   ├── models.py     # Job model + JobStatus enum
│   │   │   └── schemas.py    # Pydantic API contract (JobCreate, JobRead)
│   │   └── api/
│   │       └── routes.py     # POST /jobs, GET /jobs/{job_id}
│   └── tests/
│       ├── test_job_model.py
│       └── test_api.py
├── cli/
│   └── README.md
├── frontend/
│   └── README.md
├── infra/
│   └── docker-compose.yml
├── docs/
│   └── README.md
├── .github/
│   ├── CODEOWNERS          # required reviewers for backend, CI/CD, lockfiles, docs
│   ├── dependabot.yml      # weekly dependency updates
│   └── workflows/
│       └── ci.yml          # test + integration jobs, working-directory: backend
├── agents.md
├── LICENSE
└── README.md
```

Module responsibilities:
- `backend/app/main.py` — FastAPI app entrypoint (`/health`, `/` routes)
- `backend/app/core/config.py` — `Settings` class reading env vars (`DATABASE_URL`, `REDIS_URL`, etc.)
- `backend/app/db/session.py` — `Base`, `get_engine()`, `get_session_local()`, `get_db()` dependency
- `backend/app/jobs/models.py` — `Job` model + `JobStatus` enum (`pending`, `running`, `completed`, `failed`, `cancelled`)
- `backend/app/jobs/schemas.py` — Pydantic request/response schemas; `JobCreate.handler` bounded 1–255 to mirror the DB column
- `backend/app/api/routes.py` — `POST /jobs` (201, creates pending job), `GET /jobs/{job_id}` (200/404)
- `backend/tests/` — pytest suite (in-memory SQLite)
- `infra/docker-compose.yml` — Postgres + Redis + API + worker services
- `.github/workflows/ci.yml` — CI pipeline (test + integration jobs, working-directory: `backend`)
- `.github/dependabot.yml` — weekly dependency updates (uv + GitHub Actions)
- `.github/CODEOWNERS` — required reviewers for mergeable changes

## 6. Coding standards & tooling

- **Language:** Python 3.13+ (type hints required on public APIs)
- **Formatter/linter:** Ruff — `ruff check .` and `ruff format --check .` must pass
- **Type checker:** mypy (strict on new modules)
- **Tests:** pytest — add tests for each component; run full suite before committing
- **Migrations:** Alembic — `uv run alembic revision --autogenerate` or manual version files
- **Commit style:** Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- **Branch style:** `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`
- **Pre-commit:** run `ruff check`, `ruff format --check`, `mypy`, `pytest` before committing.

## 7. Implementation constraints (from user)

- Keep the initial implementation minimal. Don't build everything at once.
- Use environment variables for all credentials and connection strings. Include a `.env.example`, but never commit `.env`.
- Implement registered job handlers only; never execute arbitrary user-supplied Python or shell commands.
- Keep API, database, queue and worker responsibilities separated.
- Add basic tests as we implement each component.
- Document the architecture and important decisions in the README.
- **Order:** job model → database connection → migrations → job submission/retrieval → Redis → workers.
- **Do not push additional changes without showing me what was implemented and letting me review them.**

## 8. How I should work (agent workflow)

1. **Understand before writing:** Read existing code and this file before implementing anything.
2. **Small, focused changes:** One logical change per commit. Avoid giant diffs.
3. **Test everything new:** Add tests for new features/bug fixes; run the full suite before committing.
4. **Run lint + type check:** `ruff check .`, `ruff format --check .`, `mypy` on changed packages.
5. **Commit message format:** `<type>: <short summary>` with optional body. Example: `feat(api): add POST /jobs endpoint`.
6. **Push to feature branches, not directly to `main`** (unless it's the initial scaffold).
7. **Update `agents.md`** when conventions, stack, or folder structure change.
8. **Document assumptions:** If a design decision isn't specified, note it as an assumption and flag it for the user.
9. **Show before pushing:** Present implemented changes to the user for review before pushing to GitHub.

## 9. Immediate next action (Phase 3 — Redis integration + synchronous workers)

Phase 1 + Phase 2 are committed and pushed. Next:

1. Add Redis (`REDIS_URL` env var) as the job queue/broker
2. Build the **handler registry** (worker-side module mapping names → registered handler functions; registered handlers only, never arbitrary user code)
3. Synchronous worker process: dequeue from Redis, look up handler in registry, execute, update `Job` status/result/error
4. API-side: once the registry exists, validate `handler` at submission time (422 listing valid handlers) — currently deferred and documented in `create_job` docstring
5. Worker-side lifecycle for unknown/handler failures: a job stuck in `pending` (e.g. typo'd handler name submitted before registry validation) must be failed with `error` set, not left hanging
6. Alembic migration only if schema changes

Then Phase 4: concurrency, retries with exponential backoff, fault tolerance, observability.

---

*Last updated: Phase 2 complete + CI/CD added (GitHub Actions, Dependabot, CODEOWNERS, branch protection on main). All Dependabot PRs merged (action versions v7). Next: Phase 3 — Redis + workers.*