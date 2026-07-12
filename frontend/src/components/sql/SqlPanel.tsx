import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { nightOwl } from "react-syntax-highlighter/dist/esm/styles/prism";

import { ANIMATION } from "../../lib/motion";
import { useTypewriter } from "../../hooks/useTypewriter";
import { Button } from "../ui/Button";

export function SqlPanel({ sql, messageId }: { sql: string; messageId: string }) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const { displayed } = useTypewriter(sql, `${messageId}:sql`);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="mt-3 overflow-hidden rounded-md border border-border">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") setExpanded((v) => !v);
        }}
        className="flex w-full cursor-pointer items-center justify-between bg-white/5 px-3 py-1.5 text-left"
      >
        <span className="font-mono text-xs uppercase tracking-wider text-white/50">
          <span className="text-accent">{expanded ? "▾" : "▸"}</span> SQL
        </span>
        <Button
          onClick={(e) => {
            e.stopPropagation();
            handleCopy();
          }}
        >
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: ANIMATION.base, ease: ANIMATION.ease }}
            className="overflow-hidden"
          >
            <SyntaxHighlighter
              language="sql"
              style={nightOwl}
              customStyle={{ margin: 0, background: "transparent", fontSize: "0.85rem" }}
            >
              {displayed}
            </SyntaxHighlighter>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
