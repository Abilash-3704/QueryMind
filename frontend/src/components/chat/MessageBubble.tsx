import { motion } from "framer-motion";

import { useTypewriter } from "../../hooks/useTypewriter";
import { ANIMATION } from "../../lib/motion";
import type { ChatMessage } from "../../store/sessionStore";
import { ResultChart } from "../charts/ResultChart";
import { AgentPipelineViz } from "../pipeline/AgentPipelineViz";
import { SqlPanel } from "../sql/SqlPanel";
import { ClarificationPrompt } from "./ClarificationPrompt";

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return <p className="font-sans text-sm text-white/50">(0 rows)</p>;
  const columns = Object.keys(rows[0]);

  return (
    <table className="mt-2 border-collapse font-mono text-xs">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c} className="border border-border px-2 py-1 text-left text-white/70">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 20).map((row, i) => (
          <tr key={i}>
            {columns.map((c) => (
              <td key={c} className="border border-border px-2 py-1 text-white/90">
                {String(row[c])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AnswerText({ message }: { message: ChatMessage }) {
  const { displayed } = useTypewriter(message.answer ?? "", `${message.id}:answer`);
  return <div className="font-sans text-sm text-white/90">{displayed}</div>;
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: ANIMATION.base, ease: ANIMATION.ease }}
      className="mb-6"
    >
      <div className="font-sans text-sm font-semibold text-white/80">
        You: <span className="font-normal text-white/60">{message.question}</span>
      </div>

      {message.status === "pending" && (
        <div className="mt-1 font-mono text-xs text-accent/80">Thinking…</div>
      )}

      {message.status === "error" && (
        <div className="mt-1 font-sans text-sm text-red-400">Error: {message.error}</div>
      )}

      {message.status === "done" && (
        <div className="mt-2">
          <AnswerText message={message} />

          <ClarificationPrompt question={message.clarificationQuestion ?? null} />

          {message.sql && <SqlPanel sql={message.sql} messageId={message.id} />}

          {message.result && message.result.length > 0 && (
            <>
              {message.chartSpec ? (
                <ResultChart chartSpec={message.chartSpec} data={message.result} />
              ) : (
                <ResultTable rows={message.result} />
              )}
            </>
          )}

          {message.trace && message.trace.length > 0 && (
            <AgentPipelineViz
              trace={message.trace}
              retryCount={message.retryCount ?? 0}
              messageId={message.id}
            />
          )}
        </div>
      )}
    </motion.div>
  );
}
