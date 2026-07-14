import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, streamChat } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("parses SSE frames split across streamed chunks", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("event: run_started\ndata: {\"run_id\":\"r1\","));
        controller.enqueue(encoder.encode("\"chat_session_id\":\"s1\"}\n\nevent: message_delta\ndata: {\"content\":\"你好\"}\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const events: string[] = [];

    await streamChat("hello", undefined, ["doc-1"], {
      learningGoal: "掌握图算法",
      memoryEnabled: false,
      webEnabled: false,
      provider: "local",
      references: [{ type: "document", id: "doc-2", title: "第二课", collection: "material" }],
    }, (event) => events.push(event.event));

    expect(events).toEqual(["run_started", "message_delta"]);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/chat/runs", expect.objectContaining({
      body: expect.stringContaining('"document_ids":[]'),
    }));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/chat/runs", expect.objectContaining({
      body: expect.stringContaining('"preferred_document_ids":["doc-1"]'),
    }));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/chat/runs", expect.objectContaining({
      body: expect.stringContaining('"memory_enabled":false'),
    }));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/chat/runs", expect.objectContaining({
      body: expect.stringContaining('"provider":"local"'),
    }));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/chat/runs", expect.objectContaining({
      body: expect.stringContaining('"id":"doc-2"'),
    }));
  });

  it("preserves the stable API error code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: "provider_unavailable", message: "AI 尚未连接" },
    }), { status: 503, headers: { "Content-Type": "application/json" } })));

    await expect(api.settings()).rejects.toMatchObject({
      code: "provider_unavailable",
      status: 503,
      message: "AI 尚未连接",
    } satisfies Partial<ApiError>);
  });
});
