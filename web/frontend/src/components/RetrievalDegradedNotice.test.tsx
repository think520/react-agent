import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RetrievalDegradedNotice, degradedHeadline } from "./RetrievalDegradedNotice";

/**
 * W2 降级可见性：不能只说「降级了」，要说**为什么**和**下一步**。
 * 没有原因（老载荷）时也要有话说，且不能比原来更含糊。
 */

afterEach(cleanup);

describe("degradedHeadline", () => {
  it("prefers the reason's title", () => {
    expect(degradedHeadline({ title: "当前是纯文本检索（向量库被另一个进程占用）" }, 3))
      .toBe("当前是纯文本检索（向量库被另一个进程占用）");
  });

  it("falls back to the previous wording when there is no reason", () => {
    expect(degradedHeadline(undefined, 3)).toBe("当前仅使用关键词检索");
    expect(degradedHeadline(undefined, 0)).toBe("关键词检索未命中，向量检索当前不可用");
  });
});

describe("RetrievalDegradedNotice", () => {
  it("shows the headline, the facts and the next step", () => {
    render(<RetrievalDegradedNotice
      hitCount={5}
      reason={{
        code: "vector_store_locked",
        title: "当前是纯文本检索（向量库被另一个进程占用）",
        detail: "原始报错：already accessed by another instance",
        action: "关掉另一个占用该知识库的进程，再重试。",
      }}
    />);

    expect(screen.getByText(/向量库被另一个进程占用/)).toBeTruthy();
    expect(screen.getByText(/already accessed/)).toBeTruthy();
    expect(screen.getByText(/关掉另一个占用该知识库的进程/)).toBeTruthy();
    expect(screen.getByText(/下一步/)).toBeTruthy();
  });

  it("still says something useful without a reason payload", () => {
    render(<RetrievalDegradedNotice hitCount={0} />);

    expect(screen.getByText("关键词检索未命中，向量检索当前不可用")).toBeTruthy();
  });
});
