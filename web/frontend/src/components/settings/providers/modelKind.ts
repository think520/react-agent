import type { ModelKind, ProviderModel } from "../../../types";

const RERANK_TOKENS = [
  "rerank",
  "reranker",
  "bge-reranker",
  "bce-reranker",
  "jina-reranker",
  "gte-rerank",
  "cohere-rerank",
];

const EMBEDDING_TOKENS = [
  "embedding",
  "bge-m3",
  "bge-large",
  "bge-base",
  "bge-small",
  "bce-embedding",
  "text-embedding",
  "nomic-embed",
  "mxbai-embed",
  "snowflake-arctic-embed",
  "multilingual-e5",
  "e5-large",
  "e5-base",
  "e5-small",
  "m3e-",
  "gte-large",
  "gte-base",
  "gte-qwen",
  "jina-embeddings",
];

const EMBED_WORD_RE = /(?:^|[^a-z0-9])embed(?:der)?(?:$|[^a-z0-9])/;

export function classifyModelKind(modelId: string): ModelKind {
  const lower = (modelId || "").trim().toLowerCase();
  if (!lower) return "chat";
  if (RERANK_TOKENS.some((token) => lower.includes(token))) return "rerank";
  if (EMBEDDING_TOKENS.some((token) => lower.includes(token)) || EMBED_WORD_RE.test(lower)) {
    return "embedding";
  }
  return "chat";
}

export function resolveModelKind(model: Pick<ProviderModel, "id" | "kind">): ModelKind {
  if (model.kind === "chat" || model.kind === "embedding" || model.kind === "rerank") {
    return model.kind;
  }
  return classifyModelKind(model.id);
}

export function modelKindLabel(kind: ModelKind): string {
  if (kind === "embedding") return "向量";
  if (kind === "rerank") return "重排";
  return "对话";
}

export function nextModelKind(kind: ModelKind): ModelKind {
  if (kind === "chat") return "embedding";
  if (kind === "embedding") return "rerank";
  return "chat";
}
