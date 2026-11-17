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
├── backend/          # FastAPI application, workers, DB models, tests
├── cli/              # Command-line interface
├── frontend/         # Frontend application (placeholder)
├── infra/            # Docker Compose and deployment configs
├── docs/             # Documentation
├── agents.md         # AI agent working guide
├── LICENSE           # Apache-2.0
└── README.md
```

## Tech stack

- API: FastAPI (Python)
- Job store / state: PostgreSQL
- Job queue / broker: Redis
- Workers: Python background worker processes

## Getting started

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Run the API
uvicorn app.main:app --reload

# 3. Health check
curl http://localhost:8000/health
```

## License

Apache-2.0
