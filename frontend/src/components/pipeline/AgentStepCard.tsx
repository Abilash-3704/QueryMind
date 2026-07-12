import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import type { AgentStep } from "../../api/client";
import { ANIMATION } from "../../lib/motion";

export function AgentStepCard({
  step,
  pulsing = false,
}: {
  step: AgentStep;
  pulsing?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      layout
      onClick={() => setExpanded((v) => !v)}
      animate={
        pulsing
          ? {
              boxShadow: [
                "0 0 0px #00e5ff00",
                "0 0 10px #00e5ff80",
                "0 0 0px #00e5ff00",
              ],
            }
          : { boxShadow: "0 0 0px #00e5ff00" }
      }
      transition={pulsing ? { duration: 0.8, repeat: Infinity } : { duration: ANIMATION.fast }}
      className="mb-1.5 cursor-pointer rounded-md border border-border bg-panel/80 px-3 py-1.5"
    >
      <div className="flex items-center justify-between font-mono text-sm">
        <strong className={pulsing ? "text-accent" : "text-white/90"}>{step.name}</strong>
        <span className="text-white/50">{step.latency_ms.toFixed(0)} ms</span>
      </div>
      <div className="font-mono text-xs text-white/50">
        model: {step.model_used}
        {step.input_tokens != null && step.output_tokens != null && (
          <>
            {" "}
            · tokens: {step.input_tokens} in / {step.output_tokens} out
          </>
        )}
      </div>
      <AnimatePresence initial={false}>
        {expanded && (step.input_summary || step.output_summary) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: ANIMATION.base }}
            className="overflow-hidden font-mono text-xs text-white/70"
          >
            {step.input_summary && (
              <div className="mt-1.5">
                <span className="text-white/40">input: </span>
                {step.input_summary}
                {step.input_summary.length >= 400 && "…"}
              </div>
            )}
            {step.output_summary && (
              <div className="mt-1.5">
                <span className="text-white/40">output: </span>
                {step.output_summary}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
