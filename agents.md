# agents.md — TaskFlow AI Agent Working Guide

This file is written for **me (the coding agent)** to understand the TaskFlow project, how the repo is set up, how to work on it, and what conventions to follow. Keep it up to date as the project evolves.

---

## 1. Project identity

- **Name:** TaskFlow
- **Repo:** `https://github.com/MAvRK7/TaskFlow.git`
- **Working directory:** `/Users/satvikraghav/coding/TaskFlow`
- **Description:** Distributed background job processing platform built with **FastAPI**, **PostgreSQL**, **Redis**, and **Python workers**. Applications, CLI users, and AI agents submit async jobs, track execution status, and retrieve results through a unified API.
- **Core concepts explored:** job queues, concurrency, retries, fault tolerance, scalability, observability.
- **License:** Apache-2.0 (see `LICENSE`).

## 2. Repo state (as of setup)

The upstream repo originally contained only an **"Initial commit"** with two files:
- `.gitignore` (Python-focused, includes Redis/Celery/venv entries)
- `LICENSE` (Apache-2.0)

**Scaffold complete:** The folder template below has been applied and committed locally. The project now has a full directory tree with placeholder modules, entrypoint, requirements, docker-compose, and READMEs. See section 9 for the canonical tree.

Local commits ahead of `origin/main`:
- `3b10357` chore: add agents.md project guide
- `279ce26` feat: scaffold TaskFlow project structure

Push to GitHub is **blocked** — no GitHub credentials are currently configured (previous `sat-az` account logged out). You must authenticate as `MAvRK7` (`gh auth login`) before I can push.

## 3. Tech stack (target)

| Layer | Technology | Notes |
|-------|-----------|-------|
| API | FastAPI (Python) | REST API for job submission, status, results |
| Job store / state | PostgreSQL | Job definitions, execution history, results |
| Job queue / broker | Redis | Pending job queue, pub/sub for status updates |
| Workers | Python (background worker processes) | Dequeue, execute, retry, report status |
| Concurrency | asyncio / threading / multiprocessing | Per worker design TBD |
| Retries / fault tolerance | Exponential backoff, dead-letter queue | TBD |
| Observability | Logging, metrics, tracing | TBD |
| CLI | TBD | For submitting jobs from terminal |
| Client SDKs | TBD | For apps and AI agents |

## 4. Local environment

Checked on this machine (macOS):

- **Python:** 3.13.13 ✅
- **pip:** 26.1 ✅
- **Git:** configured (user: Satvik Raghav / satvikraghav007@gmail.com) ✅
- **Docker:** ❌ not installed
- **PostgreSQL (`psql`):** ❌ not installed
- **Redis (`redis-cli`):** ❌ not installed

Because Docker is unavailable, local dev should use **Homebrew** to install PostgreSQL and Redis, or the user can provide remote connection strings. Do not assume Docker Compose is available unless the user adds it.

Suggested local setup (to confirm with the user):
```bash
brew install postgresql redis
brew services start postgresql
brew services start redis
createdb taskflow
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn sqlalchemy psycopg2-binary redis alembic pytest httpx
```

## 5. Folder structure

Canonical tree (applied from your template and committed locally):

```
taskflow/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   └── __init__.py
│   │   ├── db/
│   │   │   └── __init__.py
│   │   ├── jobs/
│   │   │   └── __init__.py
│   │   └── main.py
│   ├── tests/
│   │   └── __init__.py
│   └── requirements.txt
├── cli/
│   └── README.md
├── frontend/
│   └── README.md
├── infra/
│   └── docker-compose.yml
├── docs/
│   └── README.md
├── agents.md
├── LICENSE
└── README.md
```

Module responsibilities:
- `backend/app/main.py` — FastAPI app entrypoint (`/health`, `/` routes)
- `backend/app/api/` — API route modules (to be implemented)
- `backend/app/core/` — config & utilities (to be implemented)
- `backend/app/db/` — database / SQLAlchemy setup (to be implemented)
- `backend/app/jobs/` — job models, queue logic, workers (to be implemented)
- `backend/tests/` — pytest suite
- `backend/requirements.txt` — Python dependencies
- `infra/docker-compose.yml` — Postgres + Redis + API + worker services
- `cli/`, `frontend/`, `docs/` — placeholders for future build-out

Package manager: `pip` + `requirements.txt` (default assumption; confirm if you prefer uv/poetry/pdm).

## 6. Coding standards & tooling (defaults, confirm with user)

- **Language:** Python 3.13+ (type hints required on public APIs)
- **Formatter/linter:** Ruff (fast, single tool) — prefer over black + flake8 + isort
- **Type checker:** mypy (strict on new modules)
- **Tests:** pytest
- **Test client:** httpx (for FastAPI `TestClient`/`AsyncClient`)
- **Migrations:** Alembic (if SQLAlchemy is used)
- **Commit style:** Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- **Branch style:** `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`
- **Pre-commit:** run `ruff check`, `ruff format --check`, `mypy`, `pytest` before committing.

If the user prefers a different toolchain (uv, poetry, pdm, etc.), update this section and the lock-file policy accordingly.

## 7. How I should work (agent workflow)

1. **Understand before writing:** Read existing code and this file before implementing anything.
2. **Small, focused changes:** One logical change per commit. Avoid giant diffs.
3. **Test everything new:** Add tests for new features/bug fixes; run the full suite before committing.
4. **Run lint + type check:** `ruff check .`, `ruff format --check .`, `mypy` on changed packages.
5. **Commit message format:** `<type>: <short summary>` with optional body. Example: `feat(api): add POST /jobs endpoint`.
6. **Push to feature branches, not directly to `main`** (unless it's the initial scaffold).
7. **Update `agents.md`** when conventions, stack, or folder structure change.
8. **Document assumptions:** If a design decision isn't specified, note it as an assumption and flag it for the user.

## 8. What I need from you (next steps)

1. **GitHub authentication as `MAvRK7`** — run `gh auth login` and authenticate as `MAvRK7` so I can push the local commits to `origin/main`. (Previous `sat-az` account logged out at your request.)
2. **Dependency / package manager preference** — `requirements.txt` + pip is the current default; confirm if you'd rather use uv, poetry, or pdm.
3. **Database / Redis access** — local (Homebrew) vs remote connection strings; whether to keep/add Docker Compose later.
4. **ORM / migration choice** — SQLAlchemy + Alembic (default assumption in `requirements.txt`) or raw psycopg / asyncpg.
5. **Worker execution model** — sync workers vs asyncio workers vs a queue library (RQ-style, etc.).
6. **Test strategy** — unit vs integration vs against real Postgres/Redis vs fakes/mocks.

## 9. Immediate next action

**You need to:** run `gh auth login` and authenticate as `MAvRK7`.

Once authenticated, I will:
1. `git push origin main` to publish the scaffold + agents.md
2. Then wait for your feedback on the stack choices above before implementing job models, queue logic, workers, and API routes.

---

*Last updated: initial scaffold setup. No application code present yet.*