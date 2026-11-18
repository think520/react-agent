import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SecuritySection } from "./SecuritySection";

describe("SecuritySection data boundaries", () => {
  it("explains when configured remote services may receive learning data", () => {
    render(<SecuritySection />);

    expect(screen.getByText(/远程模型仅在你主动发起请求时接收本次构造的上下文/)).toBeTruthy();
    expect(screen.getByText(/embedding.*远程服务/)).toBeTruthy();
    expect(screen.queryByText("Bobodan 不上传资料库内容，也没有账号体系；卸载前请自行备份应用数据目录。")).toBeNull();
  });
});
