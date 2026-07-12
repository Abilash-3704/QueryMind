import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import type { TableInfo } from "../../api/client";
import { ANIMATION } from "../../lib/motion";
import { useSessionStore } from "../../store/sessionStore";

function TableEntry({ table, index }: { table: TableInfo; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * ANIMATION.stagger, duration: ANIMATION.base }}
      className="mb-1"
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1 rounded px-1 py-1 text-left font-mono text-sm transition-shadow duration-200 hover:bg-white/5 hover:shadow-[0_0_12px_-2px_rgba(0,229,255,0.35)]"
      >
        <span className="text-accent">{expanded ? "▾" : "▸"}</span> {table.name}
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            layout
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: ANIMATION.base, ease: ANIMATION.ease }}
            className="overflow-hidden pl-4"
          >
            <ul className="font-mono text-xs text-white/70">
              {table.columns.map((c) => (
                <li key={c.name}>
                  {c.name} <span className="text-white/40">({c.dtype})</span>
                </li>
              ))}
            </ul>
            {table.sample_rows.length > 0 && (
              <details className="mt-1 font-mono text-xs text-white/60">
                <summary className="cursor-pointer">Sample rows</summary>
                <table className="mt-1 border-collapse">
                  <thead>
                    <tr>
                      {Object.keys(table.sample_rows[0]).map((k) => (
                        <th key={k} className="border border-border px-1.5 py-0.5 text-left">
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {table.sample_rows.map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((v, j) => (
                          <td key={j} className="border border-border px-1.5 py-0.5">
                            {String(v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

export function Sidebar() {
  const tables = useSessionStore((s) => s.tables);

  return (
    <div className="min-w-[220px] border-r border-border bg-panel/60 p-4">
      <h3 className="mb-2 font-mono text-xs uppercase tracking-wider text-white/50">
        Tables
      </h3>
      {tables.length === 0 ? (
        <p className="font-sans text-sm text-white/40">No tables loaded.</p>
      ) : (
        <ul className="list-none pl-0">
          {tables.map((t, i) => (
            <TableEntry key={t.name} table={t} index={i} />
          ))}
        </ul>
      )}
    </div>
  );
}
