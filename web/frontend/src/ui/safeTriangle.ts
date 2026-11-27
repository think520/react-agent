export interface Point {
  x: number;
  y: number;
}

export interface RectLike {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function sign(p1: Point, p2: Point, p3: Point): number {
  return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y);
}

/** Determine whether point `p` lies inside (or on edge of) triangle ABC. */
export function isPointInTriangle(p: Point, a: Point, b: Point, c: Point): boolean {
  const area = Math.abs(sign(a, b, c));
  if (area < 1e-6) return false;
  const d1 = sign(p, a, b);
  const d2 = sign(p, b, c);
  const d3 = sign(p, c, a);
  const hasNeg = d1 < 0 || d2 < 0 || d3 < 0;
  const hasPos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(hasNeg && hasPos);
}

/**
 * Check if pointer `cursor` is moving within the Safe Triangle formed by
 * `anchor` (last point on the parent menu item) and the near edge of the open submenu.
 */
export function isCursorInSubmenuSafeTriangle(
  cursor: Point,
  anchor: Point | null,
  submenuRect: RectLike | null,
  side: "right" | "left",
  padY = 8,
): boolean {
  if (!anchor || !submenuRect) return false;
  const nearX = side === "right" ? submenuRect.left : submenuRect.right;
  if (side === "right" && (cursor.x < anchor.x || nearX <= anchor.x)) return false;
  if (side === "left" && (cursor.x > anchor.x || nearX >= anchor.x)) return false;

  const topVertex: Point = { x: nearX, y: submenuRect.top - padY };
  const bottomVertex: Point = { x: nearX, y: submenuRect.bottom + padY };
  return isPointInTriangle(cursor, anchor, topVertex, bottomVertex);
}
