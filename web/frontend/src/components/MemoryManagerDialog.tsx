import { Modal } from "../ui/Modal";
import { MemoryManagerPanel } from "./settings/memory/MemoryManagerPanel";

/**
 * Notes 页仍以弹窗方式打开「管理个人知识」（2026-10-17 S4 兼容壳）。
 * 设置区已改为节内展开面板（MemorySection），不再走这个壳。
 */
export function MemoryManagerDialog({ onClose, memoryEnabled }: { onClose: () => void; memoryEnabled: boolean }) {
  return <Modal onClose={onClose} ariaLabel="管理个人知识" className="memory-manager">
    <MemoryManagerPanel memoryEnabled={memoryEnabled} onClose={onClose} />
  </Modal>;
}
