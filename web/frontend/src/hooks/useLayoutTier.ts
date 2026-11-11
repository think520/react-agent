import { useEffect, useState } from "react";

/**
 * 外壳布局只关心三个断点（768 / 972 / 1288px），不关心具体宽度。
 * 以前把 `window.innerWidth` 存进 state：窗口每拉动 1px，外壳与当前页面都整页重渲染
 * （2026-11-11 审查）。现在只在跨过断点时更新。
 */
export interface LayoutTier {
  desktop: boolean;
  leftAutoCollapsed: boolean;
  rightAutoCollapsed: boolean;
}

export function layoutTier(width: number): LayoutTier {
  return {
    desktop: width >= 768,
    leftAutoCollapsed: width < 972,
    rightAutoCollapsed: width < 1288,
  };
}

function sameTier(a: LayoutTier, b: LayoutTier) {
  return a.desktop === b.desktop && a.leftAutoCollapsed === b.leftAutoCollapsed && a.rightAutoCollapsed === b.rightAutoCollapsed;
}

export function useLayoutTier(): LayoutTier {
  const [tier, setTier] = useState(() => layoutTier(window.innerWidth));
  useEffect(() => {
    const onResize = () => {
      const next = layoutTier(window.innerWidth);
      setTier((current) => (sameTier(current, next) ? current : next));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return tier;
}
