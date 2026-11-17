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

The upstream repo currently contains only an **"Initial commit"** with two files:

- `.gitignore` (Python-focused, includes Redis/Celery/venv entries)
- `LICENSE` (Apache-2.0)

There is **no source code yet**. The repo is a blank scaffold waiting for the folder template and implementation. Do not assume any package layout exists — the folder template will come from the user next.

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

**PENDING:** The user said they will provide a folder template next. I have not imposed any layout yet.

When the template arrives, I will:
1. Create the directories and placeholder modules.
2. Add a `__init__.py` per package where appropriate.
3. Update this `agents.md` with the canonical tree and module responsibilities.
4. Add `pyproject.toml` / `requirements.txt` (or `uv`/`poetry` — to be confirmed) plus dev tooling config.

Until then, **do not create application code** beyond what is needed for setup validation.

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

## 8. What I need from the user (next steps)

1. **Folder template** — the directory/package layout for TaskFlow (api/, workers/, core/, models/, alembic/, tests/, cli/, etc.).
2. **Dependency / package manager preference** — `requirements.txt` + pip, `pyproject.toml` + uv/poetry/pdm, or something else.
3. **Database / Redis access** — local (Homebrew) vs remote connection strings; whether to add Docker Compose later.
4. **ORM / migration choice** — SQLAlchemy + Alembic (default assumption) or raw psycopg / asyncpg.
5. **Worker execution model** — sync workers vs asyncio workers vs RQ-like library.
6. **Test strategy** — unit vs integration vs against real Postgres/Redis vs fakes/mocks.

## 9. Immediate next action

Wait for the folder template, then:
1. Scaffold the directory tree + `__init__.py` files.
2. Add `pyproject.toml` / `requirements.txt` and lock file.
3. Add minimal FastAPI app entrypoint + health-check route.
4. Add Postgres + Redis connection helpers (config via env vars, `.env.example`).
5. Add `pytest` config and a smoke test.
6. Commit to a feature branch and push.

---

*Last updated: initial scaffold setup. No application code present yet.*