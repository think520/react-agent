/**
 * Session-scoped selector helpers (FE-1).
 *
 * The chat surface keeps per-session maps keyed by session id. Reading them in
 * a Zustand/selector body must:
 *   1. normalize the key (undefined new-session -> ""),
 *   2. return a stable empty-array constant for missing entries,
 * so an update to a different session never produces a new array identity and
 * never re-renders this component.
 */

export const EMPTY_ARRAY: readonly unknown[] = Object.freeze([]);

export function normalizeSessionKey(sessionId: string | undefined | null): string {
  return sessionId ?? "";
}

/** Read a per-session list with normalized key + stable empty-array fallback. */
export function sessionScopedValue<T>(
  map: Readonly<Record<string, readonly T[]>> | undefined,
  sessionId: string | undefined | null,
): readonly T[] {
  if (!map) return EMPTY_ARRAY as readonly T[];
  return map[normalizeSessionKey(sessionId)] ?? (EMPTY_ARRAY as readonly T[]);
}

/** Build a Zustand-compatible selector for a per-session list. */
export function makeSessionScopedSelector<T>(sessionId: string | undefined | null) {
  const key = normalizeSessionKey(sessionId);
  return (state: Readonly<Record<string, readonly T[]>>): readonly T[] =>
    state[key] ?? (EMPTY_ARRAY as readonly T[]);
}
