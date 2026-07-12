import { motion } from "framer-motion";

import { ANIMATION } from "../../lib/motion";

/**
 * Renders the Query Planner's clarification_needed branch. Currently a documented
 * no-op: backend/app/routes/query.py hardcodes clarification_needed=False on every
 * response, so this never fires yet — ready for when that branch is wired up.
 */
export function ClarificationPrompt({
  question,
}: {
  question: string | null;
}) {
  if (!question) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: ANIMATION.base }}
      className="mt-2 rounded-md border border-accent/40 bg-accent/10 px-3 py-2 font-sans text-sm"
    >
      <strong className="text-accent">Clarification needed:</strong> {question}
    </motion.div>
  );
}
