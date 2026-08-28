import { Keyboard } from "lucide-react";

import { Modal } from "../ui/Modal";
import { IconButton } from "./common";

const GROUPS: Array<{ title: string; items: Array<[string, string]> }> = [
  {
    title: "全局",
    items: [["Ctrl / ⌘ N", "开始新对话"]],
  },
  {
    title: "对话",
    items: [
      ["Enter", "发送"],
      ["Shift + Enter", "换行"],
      ["/", "打开命令菜单（命令与 Skills）"],
      ["@", "引用资料或会话"],
    ],
  },
  {
    title: "阅读页",
    items: [
      ["Esc", "返回资料库列表"],
      ["Shift + J / Shift + K", "下一份 / 上一份"],
      ["[ / ]", "收起 / 展开章节导轨"],
    ],
  },
  {
    title: "知识地图",
    items: [["+ / -", "扩展 / 收拢关联层级"]],
  },
  {
    title: "编辑器",
    items: [
      ["Ctrl / ⌘ \\", "切换分栏预览"],
      ["Ctrl / ⌘ Enter", "保存笔记（笔记编辑器）"],
    ],
  },
];

/** Discoverable keyboard shortcut reference, reachable from the topbar. */
export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal onClose={onClose} ariaLabel="键盘快捷键" className="shortcuts-dialog">
      <header className="shortcuts-header">
        <div><span>Shortcuts</span><h2>键盘快捷键</h2></div>
        <IconButton label="关闭快捷键" onClick={onClose}><Keyboard size={18} /></IconButton>
      </header>
      {GROUPS.map((group) => (
        <section className="shortcuts-group" key={group.title}>
          <h3>{group.title}</h3>
          <dl>
            {group.items.map(([keys, action]) => (
              <div className="shortcuts-row" key={keys}>
                <dt><kbd>{keys}</kbd></dt>
                <dd>{action}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </Modal>
  );
}
