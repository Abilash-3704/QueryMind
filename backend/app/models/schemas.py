from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Schema / DB models
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    dtype: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    sample_rows: list[dict] = Field(default_factory=list)


class SchemaInfo(BaseModel):
    tables: list[TableInfo]


# ---------------------------------------------------------------------------
# Agent I/O models
# ---------------------------------------------------------------------------

class LinkedTableColumns(BaseModel):
    """Per-table column list — avoids dict[str, list] which Groq strict mode forbids."""
    table: str
    columns: list[str]


class LinkedSchema(BaseModel):
    """Output of the Schema Linker agent."""
    table_columns: list[LinkedTableColumns]
    ambiguous: bool = False
    notes: str | None = None

    @property
    def tables(self) -> list[str]:
        return [tc.table for tc in self.table_columns]

    @property
    def columns(self) -> dict[str, list[str]]:
        return {tc.table: tc.columns for tc in self.table_columns}


class QueryPlan(BaseModel):
    """Output of the Query Planner agent."""
    steps: list[str]
    clarification_needed: bool = False
    clarification_question: str | None = None


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

class AgentStep(BaseModel):
    """One entry in the per-request trace log."""
    name: str
    model_used: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None


# ---------------------------------------------------------------------------
# Pipeline state (full schema — only a subset is populated in Phase 1)
# ---------------------------------------------------------------------------

class PipelineState(BaseModel):
    user_question: str

    # Populated by session setup (Phase 1: from hardcoded Chinook)
    schema_info: SchemaInfo | None = None

    # Agent outputs
    linked_schema: LinkedSchema | None = None
    query_plan: list[str] | None = None
    generated_sql: str | None = None

    # Execution (Phase 1: plain executor node; Phase 2: Validator agent)
    execution_result: list[dict] | None = None
    execution_error: str | None = None

    # Phase 2+
    retry_count: int = 0

    # Final outputs
    final_answer: str | None = None
    chart_spec: dict | None = None  # Phase 6

    # Observability
    trace_log: list[AgentStep] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP API models — Phase 3
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    session_id: str
    tables: list[TableInfo]
    expires_in_minutes: int
    message: str


class QueryRequest(BaseModel):
    session_id: str
    question: str


class QueryResponse(BaseModel):
    answer: str
    sql: str | None = None
    result: list[dict] | None = None
    chart_spec: dict | None = None
    trace: list[AgentStep] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str | None = None
    retry_count: int = 0
