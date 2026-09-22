from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    dtype: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    sample_rows: list[dict] = Field(default_factory=list)


class SchemaInfo(BaseModel):
    tables: list[TableInfo]


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


class AgentStep(BaseModel):
    """One entry in the per-request trace log."""
    name: str
    model_used: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None


class PipelineState(BaseModel):
    user_question: str
    schema_info: SchemaInfo | None = None

    linked_schema: LinkedSchema | None = None
    query_plan: list[str] | None = None
    generated_sql: str | None = None

    execution_result: list[dict] | None = None
    execution_error: str | None = None
    retry_count: int = 0

    final_answer: str | None = None
    chart_spec: dict | None = None

    trace_log: list[AgentStep] = Field(default_factory=list)


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
