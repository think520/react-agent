import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  RESUME_DELAYS_MS,
  api,
  documentAssetUrl,
  documentRawEmbedUrl,
  downloadDocumentRaw,
  openDocumentRaw,
  splitFrontmatter,
  streamChat,
} from "./api";

afterEach(() => vi.unstubAllGlobals());

/**
 * A stream that delivers one chunk and then breaks.
 *
 * `controller.error` on its own discards anything still queued, so the first
 * chunk has to be pulled before the failure is raised; that is also what a real
 * dropped connection looks like to the reader.
 */
function streamThatBreaks(firstFrame: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let step = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (step === 0) {
        step = 1;
        controller.enqueue(encoder.encode(firstFrame));
        return;
      }
      controller.error(new Error("network gone"));
    },
  });
}

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

  it("skips malformed SSE frames without breaking later events", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("event: run_started\ndata: {\"run_id\":\"r1\",\"chat_session_id\":\"s1\"}\n\n"));
        controller.enqueue(encoder.encode("event: message_delta\ndata: {broken json!!\n\n"));
        controller.enqueue(encoder.encode("event: message_delta\ndata: {\"content\":\"世界\"}\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const events: string[] = [];

    await streamChat("hello", undefined, [], {}, (event) => events.push(event.event));

    expect(events).toEqual(["run_started", "message_delta"]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("de-duplicates replayed frames by seq", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: message_delta\ndata: {"content":"a","seq":1,"stream_id":"s"}\n\n' +
          'event: message_delta\ndata: {"content":"b","seq":2,"stream_id":"s"}\n\n' +
          'event: message_delta\ndata: {"content":"a","seq":1,"stream_id":"s"}\n\n',
        ));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const contents: string[] = [];

    await streamChat("hello", undefined, [], {}, (event) => {
      if (event.event === "message_delta") contents.push(event.data.content);
    });

    // The duplicate seq:1 frame is skipped.
    expect(contents).toEqual(["a", "b"]);
  });

  it("resumes from the last consumed seq after the reader breaks (P0-1)", async () => {
    const encoder = new TextEncoder();
    const broken = streamThatBreaks(
      'event: run_started\ndata: {"run_id":"r1","chat_session_id":"s1","seq":1,"stream_id":"s"}\n\n' +
      'event: message_delta\ndata: {"content":"a","seq":2,"stream_id":"s"}\n\n',
    );
    const resumed = new ReadableStream<Uint8Array>({
      start(controller) {
        // seq 2 again on purpose: the client must not render it twice.
        controller.enqueue(encoder.encode(
          'event: message_delta\ndata: {"content":"a","seq":2,"stream_id":"s"}\n\n' +
          'event: message_delta\ndata: {"content":"b","seq":3,"stream_id":"s"}\n\n' +
          'event: run_completed\ndata: {"chat_session_id":"s1","termination_reason":"final_answer","seq":4,"stream_id":"s"}\n\n',
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(broken, { status: 200 }))
      .mockResolvedValueOnce(new Response(resumed, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const original = [...RESUME_DELAYS_MS];
    RESUME_DELAYS_MS.length = 0;
    RESUME_DELAYS_MS.push(0);
    const contents: string[] = [];
    const seenIds: string[] = [];

    try {
      await streamChat("hello", undefined, [], {
        onStreamId: (id) => seenIds.push(id),
      }, (event) => {
        if (event.event === "message_delta") contents.push(event.data.content);
      });
    } finally {
      RESUME_DELAYS_MS.length = 0;
      RESUME_DELAYS_MS.push(...original);
    }

    expect(contents).toEqual(["a", "b"]);
    expect(seenIds).toEqual(["s"]);
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/chat/streams/s/replay?after_seq=2");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ headers: { "Last-Event-ID": "2" } });
  });

  it("does not resume a run that already completed", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: run_started\ndata: {"run_id":"r1","chat_session_id":"s1","seq":1,"stream_id":"s"}\n\n' +
          'event: run_completed\ndata: {"chat_session_id":"s1","termination_reason":"final_answer","seq":2,"stream_id":"s"}\n\n',
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await streamChat("hello", undefined, [], {}, () => undefined);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports the original failure when it cannot resume", async () => {
    const broken = streamThatBreaks(
      'event: run_started\ndata: {"run_id":"r1","chat_session_id":"s1","seq":1,"stream_id":"s"}\n\n',
    );
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(broken, { status: 200 }))
      .mockResolvedValue(new Response("nope", { status: 502 }));
    vi.stubGlobal("fetch", fetchMock);
    const original = [...RESUME_DELAYS_MS];
    RESUME_DELAYS_MS.length = 0;
    RESUME_DELAYS_MS.push(0);

    try {
      await expect(streamChat("hello", undefined, [], {}, () => undefined))
        .rejects.toThrow("network gone");
    } finally {
      RESUME_DELAYS_MS.length = 0;
      RESUME_DELAYS_MS.push(...original);
    }

    // The primary attempt plus one resume attempt per configured delay.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("cancels a run through the stream id (P0-1)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true, cancelled: true }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.cancelRun("stream-1");

    expect(result).toEqual({ ok: true, cancelled: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/streams/stream-1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("downloads the original with its real filename (用系统打开)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("bytes", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:original"), revokeObjectURL: vi.fn() });
    const clicked: HTMLAnchorElement[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });

    await downloadDocumentRaw("doc-1", "报告.docx");

    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/documents/doc-1/raw");
    expect(clicked[0]?.download).toBe("报告.docx");
    expect(String(clicked[0]?.href)).toContain("blob:original");
    click.mockRestore();
  });

  it("reports a missing original instead of downloading an error page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 404 })));
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:original"), revokeObjectURL: vi.fn() });

    await expect(downloadDocumentRaw("gone", "x.docx")).rejects.toMatchObject({
      code: "document_raw_unavailable",
    });
  });


  it("folds YAML frontmatter instead of showing it or dropping it", () => {
    const withMeta = splitFrontmatter("---\ncourse: 数据结构\ntags: [a]\n---\n# 标题\n正文\n");
    expect(withMeta.meta).toBe("course: 数据结构\ntags: [a]");
    expect(withMeta.body.startsWith("# 标题")).toBe(true);

    const plain = splitFrontmatter("# 只是正文\n");
    expect(plain.meta).toBe("");
    expect(plain.body).toBe("# 只是正文\n");

    // A document that merely starts with a rule must not lose its first line.
    const ruleOnly = splitFrontmatter("---\n就是一条分隔线\n");
    expect(ruleOnly.meta).toBe("");
    expect(ruleOnly.body).toBe("---\n就是一条分隔线\n");
  });

  it("builds an embeddable raw URL for iframes", () => {
    expect(documentRawEmbedUrl("doc-1")).toBe("/api/kb/documents/doc-1/raw");
  });

  it("rewrites relative image sources to the asset endpoint", () => {
    expect(documentAssetUrl("doc-1", "assets/diagram.png")).toBe(
      "/api/kb/documents/doc-1/asset?path=assets%2Fdiagram.png",
    );
    expect(documentAssetUrl("doc-1", "https://example.com/x.png")).toBe("https://example.com/x.png");
    expect(documentAssetUrl("doc-1", "data:image/png;base64,AAA")).toBe("data:image/png;base64,AAA");
    expect(documentAssetUrl("doc-1", "")).toBe("");
  });

  it("reports a missing original and closes the blank tab", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 404 })));
    const target = { opener: {} as unknown, location: { href: "" }, close: vi.fn() };
    const open = vi.spyOn(window, "open").mockReturnValue(target as unknown as Window);

    await expect(openDocumentRaw("gone")).rejects.toMatchObject({
      code: "document_raw_unavailable",
      status: 404,
    });
    expect(target.close).toHaveBeenCalled();
    open.mockRestore();
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
