"""POST /query — run the LangGraph pipeline against a session's DuckDB connection."""
from __future__ import annotations

from functools import lru_cache

from app.agents.chart_selector import select_chart
from app.config import Settings, get_settings
from app.db.session_db import get_session
from app.graph.pipeline import build_graph
from app.llm_client import LLMClient
from app.models.schemas import PipelineState, QueryRequest, QueryResponse
from app.tracing import traced_session
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@lru_cache(maxsize=1)
def _get_llm_client() -> LLMClient:
    """Single LLMClient per process — avoid reconstructing SDK clients per request."""
    return LLMClient(get_settings())


def get_llm_client() -> LLMClient:
    return _get_llm_client()


@router.post("/query", response_model=QueryResponse)
def run_query(
    body: QueryRequest,
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm_client),
) -> QueryResponse:
    """Run the multi-agent text-to-SQL pipeline against an uploaded dataset."""
    ttl = settings.session_ttl_minutes * 60
    try:
        session = get_session(body.session_id, ttl_seconds=ttl)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{body.session_id}' not found.",
        )
    except TimeoutError:
        raise HTTPException(
            status_code=410,
            detail=f"Session '{body.session_id}' has expired.",
        )

    graph = build_graph(session.conn, llm, settings)
    initial = PipelineState(
        user_question=body.question,
        schema_info=session.schema_info,
    )
    with traced_session(
        body.session_id, name="query_pipeline", metadata={"question": body.question}
    ):
        result: dict = graph.invoke(initial)  # LangGraph returns a plain dict, not PipelineState

    execution_result = result.get("execution_result")
    chart_spec = select_chart(execution_result) if execution_result else None

    return QueryResponse(
        answer=result.get("final_answer") or "",
        sql=result.get("generated_sql"),
        result=execution_result,
        chart_spec=chart_spec,
        trace=result.get("trace_log", []),
        clarification_needed=False,
        clarification_question=None,
        retry_count=result.get("retry_count", 0),
    )
