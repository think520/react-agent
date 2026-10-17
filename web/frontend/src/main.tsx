import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);

// M1：字体声明（Noto 100 个分片 + 3 个 @font-face）不参与首屏关键 CSS —— 首帧用系统回退，
// 字体就位后由 font-display: swap 接上。动态 import 让打包器把它切成**独立异步 CSS chunk**。
void import("./styles/fonts.css");
