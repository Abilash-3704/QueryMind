import { motion } from "framer-motion";

import { ANIMATION } from "../../lib/motion";

export function RetryLoopIndicator({ retryCount }: { retryCount: number }) {
  if (retryCount <= 0) return null;

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: ANIMATION.fast }}
      className="ml-2 rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 font-mono text-[0.7rem] text-amber-300"
    >
      Retried {retryCount}/3
    </motion.span>
  );
}
