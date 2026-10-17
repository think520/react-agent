export interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown };
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code = "request_failed",
    public readonly status = 0,
    public readonly details?: unknown,
  ) {
    super(message);
  }
}


/**
 * 请求基座：库作用域头、错误信封、JSON 便捷方法（2026-10-17 从 lib/api.ts 抽出）。
 */

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (activeLibraryId && path.startsWith("/api/") && !path.startsWith("/api/libraries")) {
    headers.set("X-Bobodan-Library-ID", activeLibraryId);
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let body: ErrorEnvelope = {};
    try {
      body = (await response.json()) as ErrorEnvelope;
    } catch {
      // The fallback below remains user-readable when a proxy or server returns HTML.
    }
    throw new ApiError(
      body.error?.message || `请求失败 (${response.status})`,
      body.error?.code,
      response.status,
      body.error?.details,
    );
  }
  return response.json() as Promise<T>;
}

let activeLibraryId = localStorage.getItem("bobodan:library:active") || "";

export function setActiveLibraryId(libraryId: string | null) {
  activeLibraryId = libraryId || "";
  if (activeLibraryId) localStorage.setItem("bobodan:library:active", activeLibraryId);
  else localStorage.removeItem("bobodan:library:active");
}

export const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});


/** 当前生效的资料库 id（传输层/文档 URL 需要读它，写入口仍只有 setActiveLibraryId）。 */
export function getActiveLibraryId(): string {
  return activeLibraryId;
}
