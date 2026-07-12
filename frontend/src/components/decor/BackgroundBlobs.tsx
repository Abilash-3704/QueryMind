import { motion } from "framer-motion";

/**
 * Purely decorative ambient background — slow, blurred gradient blobs drifting behind
 * the UI. Deliberately on a much slower loop (20-30s) than the interaction-feedback
 * animations elsewhere (which stay in the 150-300ms range per spec §8.3) since this is
 * idle ambience, not a response to user action. Only cyan + one muted violet, kept at
 * low opacity, to stay within spec §8.1's "avoid rainbow UI, pick one accent" — this is
 * texture, not a second accent.
 */
const BLOBS = [
  { color: "#00e5ff", size: 480, top: "-14%", left: "-10%", duration: 24, delay: 0 },
  { color: "#6d5bff", size: 420, top: "38%", left: "70%", duration: 28, delay: 2 },
  { color: "#00e5ff", size: 340, top: "70%", left: "6%", duration: 32, delay: 5 },
];

export function BackgroundBlobs() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {BLOBS.map((b, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            width: b.size,
            height: b.size,
            top: b.top,
            left: b.left,
            background: b.color,
            opacity: 0.32,
            filter: "blur(70px)",
          }}
          animate={{
            x: [0, 50, -30, 0],
            y: [0, -40, 25, 0],
            scale: [1, 1.18, 0.92, 1],
          }}
          transition={{
            duration: b.duration,
            delay: b.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}
