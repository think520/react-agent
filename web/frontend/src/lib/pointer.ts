export interface PointerPosition { x: number; y: number }

/** 指针死区（M4）：按下后位移 < 4px 视为点击，≥ 4px 视为拖拽。 */
export const DRAG_DEAD_ZONE_PX = 4;

export function exceedsDragDeadZone(from: PointerPosition | null, to: PointerPosition, threshold = DRAG_DEAD_ZONE_PX): boolean {
  if (!from) return false;
  return Math.hypot(to.x - from.x, to.y - from.y) >= threshold;
}
