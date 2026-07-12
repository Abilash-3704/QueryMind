import { motion } from "framer-motion";

import { Button } from "../ui/Button";
import { useSessionStore } from "../../store/sessionStore";

export function TopBar() {
  const sessionId = useSessionStore((s) => s.sessionId);
  const clearSession = useSessionStore((s) => s.clearSession);

  return (
    <div className="relative flex items-center justify-between border-b border-border px-4 py-2">
      <strong className="font-mono text-accent tracking-wide">QueryMind</strong>
      {sessionId && (
        <span className="flex items-center gap-2 font-mono text-xs text-white/60">
          session: {sessionId.slice(0, 8)}…
          <Button onClick={clearSession}>New session</Button>
        </span>
      )}
      {/* Slow scanning highlight along the header's bottom edge — ambient, not feedback */}
      <motion.div
        className="absolute bottom-0 left-0 h-px w-full"
        style={{
          background: "linear-gradient(90deg, transparent, #00e5ff, transparent)",
          backgroundSize: "200% 100%",
        }}
        animate={{ backgroundPositionX: ["0%", "200%"] }}
        transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
      />
    </div>
  );
}
