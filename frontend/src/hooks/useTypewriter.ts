import { useEffect, useState } from "react";

import { ANIMATION } from "../lib/motion";

// Module-level, not component state — persists across re-renders/remounts so a
// message's SQL/answer typewriter plays exactly once per its lifetime, per spec
// §8.2's "the first time it appears for a given answer".
const animatedKeys = new Set<string>();

/**
 * Reveals `text` character-by-character the first time `key` is seen; every
 * subsequent render (or a different key with the same text) shows it immediately.
 */
export function useTypewriter(text: string, key: string) {
  const alreadyAnimated = animatedKeys.has(key);
  const [displayed, setDisplayed] = useState(alreadyAnimated ? text : "");
  const [done, setDone] = useState(alreadyAnimated);

  useEffect(() => {
    if (animatedKeys.has(key)) {
      setDisplayed(text);
      setDone(true);
      return;
    }
    animatedKeys.add(key);

    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setDone(true);
      }
    }, ANIMATION.typewriterMsPerChar);

    return () => clearInterval(interval);
    // Intentionally re-running only when key/text identity changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, text]);

  return { displayed, done };
}
