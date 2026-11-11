import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "../../types";

// 统计 react-markdown 被调用的次数：每次调用 = 一次 Markdown 解析。
const markdownCalls = vi.hoisted(() => ({ count: 0 }));
vi.mock("react-markdown", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-markdown")>();
  const Wrapped = (props: Parameters<typeof actual.default>[0]) => {
    markdownCalls.count += 1;
    return actual.default(props);
  };
  return { ...actual, default: Wrapped };
});

import { ChatTranscript } from "./ChatTranscript";

afterEach(cleanup);

function transcript(messages: ChatMessage[]) {
  // 故意每次给新的回调：ChatPage 就是这样传的。
  return <MemoryRouter>
    <ChatTranscript
      messages={messages}
      status="正在整理"
      brandState="writing"
      assistantName="Bobodan"
      sending
      error=""
      truncated={null}
      onContinue={() => undefined}
      onPreparePractice={() => undefined}
      onRetry={() => undefined}
      renderArtifact={() => null}
      onOpenReference={() => undefined}
      onOpenSources={() => undefined}
    />
  </MemoryRouter>;
}

describe("ChatTranscript streaming cost", () => {
  it("re-parses only the message that is still streaming", () => {
    const history: ChatMessage[] = Array.from({ length: 6 }, (_, index) => ({
      role: index % 2 ? "assistant" : "user",
      content: `第 ${index} 条 **历史**`,
    }));
    const streaming = (content: string): ChatMessage => ({ role: "assistant", content, pending: true });

    const view = render(transcript([...history, streaming("正在")]));
    markdownCalls.count = 0;

    view.rerender(transcript([...history, streaming("正在写")]));
    view.rerender(transcript([...history, streaming("正在写回答")]));

    // 3 条历史助手消息不应再解析；只有正在流式的那条每次刷新解析一次。
    expect(markdownCalls.count).toBe(2);
  });
});
