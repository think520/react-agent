/** Normalizes an unknown thrown value into a user-facing message. */
export function toErrorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}
