/**
 * Typed fetch wrappers for the QueryMind backend. Types mirror
 * backend/app/models/schemas.py field-for-field — no transformation layer.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ColumnInfo {
  name: string;
  dtype: string;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  sample_rows: Record<string, unknown>[];
}

export interface UploadResponse {
  session_id: string;
  tables: TableInfo[];
  expires_in_minutes: number;
  message: string;
}

export interface AgentStep {
  name: string;
  model_used: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  input_summary: string | null;
  output_summary: string | null;
}

export interface ChartSpec {
  type: string;
  x: string;
  y: string;
}

export interface QueryResponse {
  answer: string;
  sql: string | null;
  result: Record<string, unknown>[] | null;
  chart_spec: ChartSpec | null;
  trace: AgentStep[];
  clarification_needed: boolean;
  clarification_question: string | null;
  retry_count: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return res.statusText;
  }
}

export async function uploadCsv(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);

  const res = await fetch(`${BASE_URL}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

export async function runQuery(
  sessionId: string,
  question: string,
): Promise<QueryResponse> {
  const res = await fetch(`${BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

export async function getEvalReport(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE_URL}/eval-report`);
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}
