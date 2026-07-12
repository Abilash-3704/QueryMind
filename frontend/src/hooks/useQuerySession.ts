import { useCallback } from "react";

import { ApiError, runQuery, uploadCsv } from "../api/client";
import { useSessionStore } from "../store/sessionStore";

/**
 * The only place components call the backend. Wraps the API client with
 * store updates, so components never touch fetch() or the store's setters
 * directly.
 */
export function useQuerySession() {
  const sessionId = useSessionStore((s) => s.sessionId);
  const tables = useSessionStore((s) => s.tables);
  const messages = useSessionStore((s) => s.messages);
  const isUploading = useSessionStore((s) => s.isUploading);
  const isQuerying = useSessionStore((s) => s.isQuerying);

  const upload = useCallback(async (files: File[]) => {
    useSessionStore.getState().setUploading(true);
    try {
      const res = await uploadCsv(files);
      useSessionStore.getState().setSession(res.session_id, res.tables);
    } finally {
      useSessionStore.getState().setUploading(false);
    }
  }, []);

  const ask = useCallback(async (question: string) => {
    const { sessionId: sid, addMessage, updateMessage, setQuerying } =
      useSessionStore.getState();
    if (!sid) return;

    const id = crypto.randomUUID();
    addMessage({ id, question, status: "pending" });
    setQuerying(true);

    try {
      const res = await runQuery(sid, question);
      updateMessage(id, {
        status: "done",
        answer: res.answer,
        sql: res.sql,
        result: res.result,
        chartSpec: res.chart_spec,
        trace: res.trace,
        retryCount: res.retry_count,
        clarificationQuestion: res.clarification_question,
      });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.status === 410 ? "Session expired" : "Query failed"}: ${err.message}`
          : "Query failed: unexpected error";
      updateMessage(id, { status: "error", error: message });
    } finally {
      setQuerying(false);
    }
  }, []);

  return { sessionId, tables, messages, isUploading, isQuerying, upload, ask };
}
