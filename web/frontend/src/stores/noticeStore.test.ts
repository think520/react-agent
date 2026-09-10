import { beforeEach, describe, expect, it } from "vitest";

import { MAX_NOTICES, useNoticeStore } from "./noticeStore";

describe("noticeStore", () => {
  beforeEach(() => {
    useNoticeStore.getState().clearNotices();
  });

  it("pushes an error notice by default", () => {
    useNoticeStore.getState().pushNotice({ message: "无法切换模型。" });

    const notices = useNoticeStore.getState().notices;
    expect(notices).toHaveLength(1);
    expect(notices[0].message).toBe("无法切换模型。");
    expect(notices[0].tone).toBe("error");
    expect(notices[0].id).toBeTruthy();
  });

  it("trims and ignores empty messages", () => {
    useNoticeStore.getState().pushNotice({ message: "   " });
    expect(useNoticeStore.getState().notices).toHaveLength(0);
  });

  it("does not stack an identical message twice", () => {
    useNoticeStore.getState().pushNotice({ message: "联网搜索暂时不可用。" });
    useNoticeStore.getState().pushNotice({ message: "联网搜索暂时不可用。" });
    expect(useNoticeStore.getState().notices).toHaveLength(1);
  });

  it("keeps only the newest notices", () => {
    for (let index = 0; index < MAX_NOTICES + 2; index += 1) {
      useNoticeStore.getState().pushNotice({ message: `失败 ${index}` });
    }
    const notices = useNoticeStore.getState().notices;
    expect(notices).toHaveLength(MAX_NOTICES);
    expect(notices.at(-1)?.message).toBe(`失败 ${MAX_NOTICES + 1}`);
  });

  it("dismisses one notice by id and clears the rest", () => {
    useNoticeStore.getState().pushNotice({ message: "第一处失败" });
    useNoticeStore.getState().pushNotice({ message: "第二处失败" });
    const first = useNoticeStore.getState().notices[0];
    useNoticeStore.getState().dismissNotice(first.id);
    expect(useNoticeStore.getState().notices.map((notice) => notice.message)).toEqual(["第二处失败"]);

    useNoticeStore.getState().clearNotices();
    expect(useNoticeStore.getState().notices).toHaveLength(0);
  });
});
