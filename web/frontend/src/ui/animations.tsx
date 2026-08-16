import { type ReactNode } from "react";

/**
 * Animation primitives (FE-1). Business components import these from @/ui only,
 * so swapping the animation implementation (e.g. to the motion library) is a
 * one-file change. Everything honors prefers-reduced-motion via CSS.
 */

export function FadeIn({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ui-anim ui-fade-in ${className}`}>{children}</div>;
}

export function Collapse({ open, children, className = "" }: { open: boolean; children: ReactNode; className?: string }) {
  return (
    <div className={`ui-anim ui-collapse ${open ? "open" : ""} ${className}`} aria-hidden={!open}>
      {children}
    </div>
  );
}

export function SlideIn({ children, className = "", direction = "up" }: { children: ReactNode; className?: string; direction?: "up" | "left" }) {
  return <div className={`ui-anim ui-slide-in ui-slide-${direction} ${className}`}>{children}</div>;
}

export function AnimatedList({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ui-anim ui-animated-list ${className}`}>{children}</div>;
}
