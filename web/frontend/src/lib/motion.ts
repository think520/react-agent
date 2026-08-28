/**
 * Single source of truth for "user prefers less motion": the OS-level
 * prefers-reduced-motion media query OR the in-app 界面感受 toggle (written to
 * data-motion on <html> by AppShell). Always read live — settings can change
 * mid-session.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return true;
  } catch {
    // matchMedia unavailable: fall through to the in-app flag only.
  }
  return document.documentElement.dataset.motion === "reduced";
}
