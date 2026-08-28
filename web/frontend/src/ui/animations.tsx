import { type ReactNode } from "react";

/**
 * Animation primitive (FE-1). Business components import this from @/ui only,
 * so swapping the animation implementation (e.g. to the motion library) is a
 * one-file change. Honors prefers-reduced-motion via CSS.
 *
 * Collapse / SlideIn / AnimatedList were removed: they never gained a
 * consumer. Reintroduce only when a surface actually needs them.
 */

export function FadeIn({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ui-anim ui-fade-in ${className}`}>{children}</div>;
}
