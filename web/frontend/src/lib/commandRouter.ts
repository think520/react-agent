/**
 * Pure routing for slash commands typed into the chat composer.
 * The page decides how to execute the returned route (navigation,
 * API calls, hand-offs); this module only classifies the message.
 */

export type CommandRoute =
  | { kind: "none" }
  | { kind: "navigate"; to: string }
  | { kind: "practice-topic"; topic: string }
  | { kind: "wiki-generate" }
  | { kind: "wiki-focus"; action: "generate" | "update"; instruction: string }
  | { kind: "web-search"; query: string }
  | { kind: "web-search-empty" };

export function routeSlashCommand(message: string, options: { webOnce?: boolean } = {}): CommandRoute {
  if (message === "/new") return { kind: "navigate", to: "/chat" };
  if (message === "/library") return { kind: "navigate", to: "/library" };
  if (message === "/wiki") return { kind: "navigate", to: "/library?collection=wiki" };
  if (message === "/wiki generate") return { kind: "wiki-generate" };
  if (message === "/wiki plan" || message.startsWith("/wiki plan ")) {
    return { kind: "wiki-focus", action: "generate", instruction: message.slice("/wiki plan".length).trim() };
  }
  if (message === "/wiki update" || message.startsWith("/wiki update ")) {
    return { kind: "wiki-focus", action: "update", instruction: message.slice("/wiki update".length).trim() };
  }
  if (message === "/practice") return { kind: "navigate", to: "/practice" };
  if (message === "/review") return { kind: "navigate", to: "/review" };
  if (message.startsWith("/quiz generate ")) {
    return { kind: "practice-topic", topic: message.slice("/quiz generate ".length).trim() };
  }
  if (options.webOnce || message === "/web search" || message.startsWith("/web search ")) {
    const query = message.startsWith("/web search") ? message.slice("/web search".length).trim() : message;
    return query ? { kind: "web-search", query } : { kind: "web-search-empty" };
  }
  return { kind: "none" };
}
