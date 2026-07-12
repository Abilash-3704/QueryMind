import { motion } from "framer-motion";
import type { ButtonHTMLAttributes } from "react";

import { ANIMATION } from "../../lib/motion";

// framer-motion's gesture/animation props (onDrag*, onAnimation*) collide with the
// native DOM event props of the same name — omit the native ones since this
// component doesn't use native HTML5 drag-and-drop or CSS animation events.
type NativeButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  | "onDrag"
  | "onDragStart"
  | "onDragEnd"
  | "onAnimationStart"
  | "onAnimationEnd"
  | "onAnimationIteration"
>;

type ButtonProps = NativeButtonProps & {
  variant?: "primary" | "ghost";
};

/**
 * Shared button with the hover/tap micro-interaction spec §8.3 asks for, defined
 * once here rather than repeated on every `<button>` instance.
 */
export function Button({ variant = "ghost", className = "", ...props }: ButtonProps) {
  const base =
    "rounded-md px-3 py-1.5 text-sm font-sans transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-accent text-black font-medium hover:bg-accent/90",
    ghost: "bg-white/5 text-white border border-border hover:bg-white/10",
  };

  return (
    <motion.button
      whileHover={props.disabled ? undefined : { scale: 1.02 }}
      whileTap={props.disabled ? undefined : ANIMATION.micro}
      transition={{ duration: ANIMATION.fast }}
      className={`${base} ${variants[variant]} ${className}`}
      {...props}
    />
  );
}
