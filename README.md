# TaskFlow

Distributed background job processing platform built with **FastAPI**, **PostgreSQL**, **Redis**, and **Python workers**.

Enables applications, CLI users, and AI agents to submit asynchronous jobs, track execution status, and retrieve results through a unified API.

## Project explores

- Job queues
- Concurrency
- Retries & fault tolerance
- Scalability
- Observability

## Repository layout

```
taskflow/
├── backend/          # FastAPI application, workers, DB models, tests (uv-managed)
├── cli/              # Command-line interface (placeholder)
├── frontend/         # Frontend application (placeholder)
├── infra/            # Docker Compose and deployment configs
├── docs/             # Documentation
├── agents.md         # AI agent working guide
├── LICENSE           # Apache-2.0
└── README.md
```

## Tech stack

| Layer | Technology | Decision |
|-------|-----------|----------|
| API | FastAPI (Python 3.13) | REST API for job submission, status, results |
| Job store / state | PostgreSQL (Supabase) | Connection via `DATABASE_URL` env var |
| Job queue / broker | Redis | Connection via `REDIS_URL` env var; Docker locally |
| Workers | Python (synchronous, separate processes) | Modular; concurrency added later |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | `app/db/session.py`, `alembic/` |
| Package manager | uv | `pyproject.toml` + `uv.lock` |
| Config | Environment variables | `.env.example` template; `.env` never committed |
| Tests | pytest | In-memory SQLite for unit tests |

## Architecture decisions

- **Env vars for all credentials:** `DATABASE_URL` and `REDIS_URL` are read from the environment. Copy `.env.example` to `.env` and fill in your values. `.env` is gitignored and must never be committed.
- **Registered job handlers only:** Workers execute only registered handlers. Arbitrary user-supplied Python or shell commands are never executed.
- **Separated responsibilities:** API layer (routes), database layer (SQLAlchemy models/session), queue layer (Redis), and worker layer (job execution) are kept in separate modules under `backend/app/`.
- **Synchronous workers initially:** Workers run as separate Python processes, dequeuing jobs and executing handlers synchronously. The architecture is modular so concurrency/async workers can be introduced later.
- **Minimal initial implementation:** Phase 1 delivers the job model, database connection, and Alembic migrations. Job submission/retrieval comes next; Redis and workers follow.

## Backend layout

```
backend/
├── pyproject.toml      # uv project config + dependencies
├── uv.lock             # locked dependency versions (committed)
├── .env.example        # environment variable template (copy to .env)
├── alembic.ini         # Alembic config
├── alembic/
│   ├── env.py          # loads .env, sets target_metadata from app.db.session.Base
│   └── versions/
│       └── 0001_create_jobs_table.py
├── app/
│   ├── __init__.py
│   ├── main.py         # FastAPI entrypoint (/health, /)
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py   # Settings from environment variables
│   ├── db/
│   │   ├── __init__.py
│   │   └── session.py  # SQLAlchemy engine, session, Base
│   ├── jobs/
│   │   ├── __init__.py
│   │   └── models.py   # Job model + JobStatus enum
│   └── api/            # route modules (to be implemented)
├── tests/
│   └── test_job_model.py
```

## Getting started (backend)

```bash
cd backend

# 1. Install dependencies with uv
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your Supabase DATABASE_URL and local Redis REDIS_URL

# 3. Run migrations (requires a reachable DATABASE_URL)
uv run alembic upgrade head

# 4. Run the API
uv run uvicorn app.main:app --reload

# 5. Health check
curl http://localhost:8000/health

# 6. Run tests (in-memory SQLite, no live DB needed)
uv run pytest tests/
```

## License

Apache-2.0

## AI agent guidance

See [`agents.md`](agents.md) for the working guide used when developing this project.
