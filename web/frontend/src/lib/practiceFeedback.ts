function normalized(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function distinctExplanation(feedback: string, explanation: string): string {
  const compactExplanation = normalized(explanation);
  if (!compactExplanation) return "";
  return normalized(feedback).includes(compactExplanation) ? "" : explanation;
}
