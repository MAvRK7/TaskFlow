"""TaskFlow FastAPI application entrypoint.

Distributed background job processing platform.
"""

from fastapi import FastAPI

from app.api.routes import router
from app.jobs.registry import load_builtin_handlers

# The registry is process-local and populated by import side effects, so the
# API process loads the built-in handlers before it starts validating
# submissions (design doc §5.1).
load_builtin_handlers()

app = FastAPI(
    title="TaskFlow",
    description="Distributed background job processing platform",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint."""
    return {"message": "Welcome to TaskFlow"}
