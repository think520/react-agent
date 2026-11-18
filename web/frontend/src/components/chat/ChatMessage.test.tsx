import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import type { ChatMessage } from "../../types";
import { AssistantMessage } from "./ChatMessage";

describe("AssistantMessage citations", () => {
  it("renders citation-like code literally and links only the prose marker", () => {
    const message: ChatMessage = {
      role: "assistant",
      content: "正文 [Sa1b2c3]，行内代码 `[Sa1b2c3]`。\n\n```ts\nconst cite = \"[Sa1b2c3]\";\n```",
      attribution: {
        kind: "local",
        status: "found",
        sources: [{ source_type: "local", source_id: "c1", title: "示例讲义", document_id: "doc1", chunk_id: "chunk1", cite_label: "Sa1b2c3" }],
      },
    };
    const { container } = render(<MemoryRouter><AssistantMessage
      message={message}
      index={0}
      assistantName="Bobodan"
      status={null}
      brandState={"ready" as ProcessBrandState}
      sending={false}
      error=""
      onPreparePractice={vi.fn()}
      onRetry={vi.fn()}
      renderArtifact={() => null}
      onOpenSources={vi.fn()}
    /></MemoryRouter>);

    expect(container.querySelectorAll(".citation-mark")).toHaveLength(1);
    expect(container.querySelector("code")?.textContent).toBe("[Sa1b2c3]");
    expect(container.querySelector("pre code")?.textContent?.trimEnd()).toBe('const cite = "[Sa1b2c3]";');
  });
});
