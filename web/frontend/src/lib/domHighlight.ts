/**
 * W1 E7：把划线画在**正文里**（DOM 装饰）。
 *
 * 关键取舍：正文是 markdown **渲染后**的文字，而锚点存的偏移是**原文**偏移 ——
 * 两者对不上（渲染会吃掉 \`**\`、\`#\`）。所以在 DOM 里按**引文**定位：
 * 引文本来就是从这段正文里选出来的，一定能在渲染后的文字里找到；找不到就不画
 * （宁可不画，也不要画错地方）。
 */

export const HIGHLIGHT_CLASS = "reader-anchor-mark";

interface TextPosition {
  node: Text;
  start: number;
}

function collectTextNodes(root: Node): TextPosition[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.parentElement?.closest(`mark.${HIGHLIGHT_CLASS}`)
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
  });
  const positions: TextPosition[] = [];
  let offset = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node as Text;
    positions.push({ node: text, start: offset });
    offset += text.data.length;
  }
  return positions;
}

/** 把「整段文本里的第 start..end 个字符」映射回具体的文本节点。 */
function locate(positions: TextPosition[], index: number): { node: Text; offset: number } | null {
  for (let cursor = positions.length - 1; cursor >= 0; cursor -= 1) {
    const position = positions[cursor];
    if (index >= position.start) {
      return { node: position.node, offset: Math.min(index - position.start, position.node.data.length) };
    }
  }
  return null;
}

/** 在 root 里给第一处**还没被标记过**的引文画上线；返回是否画到了。 */
export function highlightQuote(root: Element, quote: string, className = HIGHLIGHT_CLASS): boolean {
  const needle = quote.trim();
  if (!needle) return false;

  const positions = collectTextNodes(root);
  const text = positions.map((position) => position.node.data).join("");
  const found = text.indexOf(needle);
  if (found < 0) return false;

  const start = locate(positions, found);
  const end = locate(positions, found + needle.length);
  if (!start || !end) return false;

  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset);

  const mark = document.createElement("mark");
  mark.className = className;
  // 记下是哪条引文：阅读器据此做幂等重画（已有就不重复包）。
  mark.dataset.quote = needle;
  try {
    // extractContents 会按需切开文本节点（引文跨 <strong> 也能画）。
    mark.appendChild(range.extractContents());
    range.insertNode(mark);
  } catch {
    return false;
  }
  return true;
}

/** 撤掉一条划线上色（正文文字保持不变）。不 normalize：DOM 归 React 管，别合并它跟踪的文本节点。 */
export function unwrapHighlight(mark: Element): void {
  const parent = mark.parentNode;
  if (!parent) return;
  while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
  parent.removeChild(mark);
}

/** 撤掉所有划线上色（正文文字保持不变）。 */
export function clearHighlights(root: Element, className = HIGHLIGHT_CLASS): void {
  root.querySelectorAll(`mark.${className}`).forEach((mark) => unwrapHighlight(mark));
}
