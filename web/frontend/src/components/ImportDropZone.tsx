import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { Upload } from "lucide-react";

interface ImportDropZoneProps {
  onFiles: (files: File[]) => void;
  /** 没有资料库时不该摆热区（先让用户建/接资料库）。 */
  enabled?: boolean;
  children: ReactNode;
}

/**
 * E8：导入的拖拽热区。
 *
 * 参考 openhanako 的 desk 拖拽：用**计数器**而不是布尔值（dragenter/dragleave 会在子元素
 * 之间成对抖动），并且必须在 window 上兜 drop / dragend / blur —— 松手在窗口外、按 Escape
 * 或切走窗口时收不到成对的 dragleave，只靠组件事件的话计数器会卡在 1，覆盖层再也退不掉。
 */
export function ImportDropZone({ onFiles, enabled = true, children }: ImportDropZoneProps) {
  const [active, setActive] = useState(false);
  const depth = useRef(0);

  const reset = () => {
    depth.current = 0;
    setActive(false);
  };

  useEffect(() => {
    // 窗口级兜底：这三个事件一定会来，哪怕拖拽在窗口外结束。
    window.addEventListener("dragend", reset);
    window.addEventListener("drop", reset);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("dragend", reset);
      window.removeEventListener("drop", reset);
      window.removeEventListener("blur", reset);
    };
  }, []);

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    if (!enabled || !event.dataTransfer?.types?.includes("Files")) return;
    event.preventDefault();
    depth.current += 1;
    setActive(true);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (!enabled) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave() {
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setActive(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const files = Array.from(event.dataTransfer?.files || []);
    reset();
    if (!enabled || !files.length) return;
    onFiles(files);
  }

  return (
    <div
      className={`import-drop-zone${active ? " is-active" : ""}`}
      data-testid="import-drop-zone"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}
      {active && (
        <div className="import-drop-overlay" role="status">
          <Upload size={18} />
          <span>松开就导入到资料库</span>
        </div>
      )}
    </div>
  );
}
