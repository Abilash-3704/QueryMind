import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

import type { AgentStep } from "../../api/client";
import { ANIMATION } from "../../lib/motion";
import { AgentStepCard } from "./AgentStepCard";
import { RetryLoopIndicator } from "./RetryLoopIndicator";

/**
 * The Validator agent is pure code (no LLM call) — it never appends to trace_log, so
 * there's no literal "validator" entry to render. A retry shows up only as a second
 * "sql_generator" entry in the trace; we render that as an implicit validator rejection
 * (with a loop-back arrow) between the two SQL Generator cards.
 *
 * No SSE/real-time push exists yet (spec §8.4's optional stretch), so this can't animate
 * live as the backend actually executes. Instead it replays once the full response has
 * already arrived, timed proportionally to each step's real `latency_ms` — compressed into
 * a fixed ~1s budget (ANIMATION.pipelineReplayMs) so it stays snappy rather than taking as
 * long as the real request did. Genuinely driven by real timing data, just not live.
 */
const STAGE_LABELS: Record<string, string> = {
  schema_linker: "Schema Linker",
  query_planner: "Query Planner",
  sql_generator: "SQL Generator",
  explainer: "Explainer",
};

const STAGE_ORDER = ["schema_linker", "query_planner", "sql_generator", "explainer"];

// Module-level — tracks which messages have already played their pipeline reveal,
// mirroring useTypewriter's pattern, so re-renders/remounts don't replay it.
const animatedPipelines = new Set<string>();

interface FlatStep {
  key: string;
  stageName: string;
  step: AgentStep;
  attemptIndex: number;
  cumulativeLatency: number;
}

function RetryLoopArrow() {
  return (
    <svg width="20" height="14" viewBox="0 0 20 14" className="text-amber-400">
      <motion.path
        d="M2,2 Q10,14 18,2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="24"
        initial={{ strokeDashoffset: 24 }}
        animate={{ strokeDashoffset: 0 }}
        transition={{ duration: ANIMATION.slow }}
      />
      <path d="M15,1 L18,2 L16.5,4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function AgentPipelineViz({
  trace,
  retryCount,
  messageId,
}: {
  trace: AgentStep[];
  retryCount: number;
  messageId: string;
}) {
  const alreadyAnimated = animatedPipelines.has(messageId);

  const flat = useMemo<FlatStep[]>(() => {
    const byName = new Map<string, AgentStep[]>();
    for (const step of trace) {
      const list = byName.get(step.name) ?? [];
      list.push(step);
      byName.set(step.name, list);
    }
    const result: FlatStep[] = [];
    let cumulative = 0;
    for (const name of STAGE_ORDER) {
      const steps = byName.get(name);
      if (!steps) continue;
      steps.forEach((step, i) => {
        cumulative += step.latency_ms;
        result.push({
          key: `${name}-${i}`,
          stageName: name,
          step,
          attemptIndex: i,
          cumulativeLatency: cumulative,
        });
      });
    }
    return result;
  }, [trace]);

  const totalLatency = flat.length > 0 ? flat[flat.length - 1].cumulativeLatency : 1;

  const delays = useMemo(() => {
    const raw = flat.map(
      (f) => (f.cumulativeLatency / totalLatency) * ANIMATION.pipelineReplayMs,
    );
    const spaced: number[] = [];
    let prev = 0;
    for (const d of raw) {
      const next = Math.max(d, prev + ANIMATION.pipelineMinStepMs);
      spaced.push(next);
      prev = next;
    }
    return spaced;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flat, totalLatency]);

  const [activeIndex, setActiveIndex] = useState(alreadyAnimated ? flat.length - 1 : -1);

  useEffect(() => {
    if (alreadyAnimated) return;
    animatedPipelines.add(messageId);
    const timers = delays.map((delay, i) => setTimeout(() => setActiveIndex(i), delay));
    return () => timers.forEach(clearTimeout);
    // Deliberately only re-running when the message changes, not on every delay recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messageId]);

  const visibleCount = alreadyAnimated ? flat.length : activeIndex + 1;
  let lastStage = "";

  return (
    <div className="mt-3 rounded-md border border-border bg-white/5 p-3 backdrop-blur-sm">
      <h4 className="mb-1 font-mono text-xs uppercase tracking-wider text-white/50">
        Agent Pipeline
      </h4>
      {flat.slice(0, visibleCount).map((f, i) => {
        const showHeader = f.stageName !== lastStage;
        lastStage = f.stageName;
        const isActive = !alreadyAnimated && i === visibleCount - 1;

        return (
          <div key={f.key}>
            {showHeader && (
              <div className="mb-1 mt-2 flex items-center font-mono text-sm text-white/80">
                {STAGE_LABELS[f.stageName] ?? f.stageName}
                {f.stageName === "sql_generator" && (
                  <RetryLoopIndicator retryCount={retryCount} />
                )}
              </div>
            )}
            {f.attemptIndex > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mb-1 flex items-center gap-1.5 font-mono text-xs text-amber-400"
              >
                <RetryLoopArrow />
                Validator rejected attempt {f.attemptIndex} — retrying SQL Generator
              </motion.div>
            )}
            <AgentStepCard step={f.step} pulsing={isActive} />
          </div>
        );
      })}
    </div>
  );
}
