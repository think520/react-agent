/**
 * API 门面：调用方继续 «from "../lib/api"» 拿一切（2026-10-17 M2 拆分）。
 * 实现分散在 ./api/{http,types,transport}.ts 与 ./api/endpoints/*.ts。
 */
import { chatApi } from "./api/endpoints/chat";
import { libraryApi } from "./api/endpoints/library";
import { practiceApi } from "./api/endpoints/practice";
import { wikiApi } from "./api/endpoints/wiki";
import { workspaceApi } from "./api/endpoints/workspace";

export * from "./api/http";
export * from "./api/types";
export * from "./api/transport";

export const api = {
  ...libraryApi,
  ...chatApi,
  ...wikiApi,
  ...practiceApi,
  ...workspaceApi,
};
