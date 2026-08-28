/**
 * Sticky-bottom scroll easing math (FE-2). Pure, testable helpers shared by
 * the continuous bottom-scroll hook.
 */

export const TAU_MS = 85;
export const INSTANT_JUMP_THRESHOLD = 720;

/** Exponential easing factor toward the target for one frame. */
export function easingFactor(deltaMs: number, tauMs = TAU_MS): number {
  if (deltaMs <= 0) return 0;
  return 1 - Math.exp(-deltaMs / tauMs);
}

/** True when the distance is large enough to jump instantly. */
export function shouldJumpInstant(distance: number, threshold = INSTANT_JUMP_THRESHOLD): boolean {
  return Math.abs(distance) > threshold;
}

/** Compute the next scroll position after one easing step toward target. */
export function easedPosition(current: number, target: number, factor: number): number {
  return current + (target - current) * factor;
}
