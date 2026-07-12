"""FastAPI application entrypoint for QueryMind."""
from __future__ import annotations

from app.routes.eval import router as eval_router
from app.routes.query import router as query_router
from app.routes.upload import router as upload_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="QueryMind",
    description="Multi-agent text-to-SQL analyst",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, tags=["upload"])
app.include_router(query_router, tags=["query"])
app.include_router(eval_router, tags=["eval"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
