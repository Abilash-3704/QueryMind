/**
 * Shared animation timing constants (spec §8.3: "keep animations fast (150–300ms)
 * — this should feel snappy/technical, not slow or gimmicky"). Every component
 * pulls from here instead of scattering magic numbers.
 */
export const ANIMATION = {
  fast: 0.15,
  base: 0.2,
  slow: 0.3,
  stagger: 0.05,
  micro: { scale: 0.98 },
  ease: "easeOut" as const,

  /** Total budget for the pipeline visualizer's replayed-timing intro (ms). */
  pipelineReplayMs: 1000,
  /** Floor so a very fast real step is still visible during the replay. */
  pipelineMinStepMs: 120,

  /** Typewriter reveal speed (ms per character). */
  typewriterMsPerChar: 12,
};
