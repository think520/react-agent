/**
 * W3 F7：自动滚动的**决策**（纯函数）。
 *
 * 为什么要把决策抽出来：jsdom 没有布局（scrollHeight 恒为 0），任何「滚不滚」的判断
 * 放在 DOM 里就测不了；而这段逻辑恰恰是最容易出错的（抢滚动、手势里抢、用户滚上去
 * 之后再也不跟随）。hook 只负责把这里的决策接到 rAF / MutationObserver / 手势上。
 */

import { shouldJumpInstant } from "./scrollEasing";

/** 离底部多少像素以内算「还在底部」——沿用既有行为（40px）。 */
export const FOLLOW_THRESHOLD_PX = 40;

export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/** 离底部还有多少像素；过卷（内容变短）时算 0，不返回负数。 */
export function distanceFromBottom(metrics: ScrollMetrics): number {
  const raw = metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight;
  return raw > 0 ? raw : 0;
}

export interface FollowInput {
  metrics: ScrollMetrics;
  /** 用户正在进行触摸/滚轮手势 —— 手势期间绝不写滚动位置。 */
  interacting: boolean;
  /** 用户刚发了消息（或显式要求）—— 无条件回到跟随。 */
  pinned: boolean;
}

/**
 * 要不要跟随新内容。三条规则，优先级从高到低：
 * 1) 手势中 → 不跟随（谁也不能在用户手指底下抢滚动）；
 * 2) 用户刚发消息（pinned）→ 跟随（即使之前滚到上面去了）；
 * 3) 本来就在底部附近 → 跟随；否则不打扰。
 */
export function shouldFollow(input: FollowInput): boolean {
  if (input.interacting) return false;
  if (input.pinned) return true;
  return distanceFromBottom(input.metrics) < FOLLOW_THRESHOLD_PX;
}

/** 大跳变直接瞬移（沿用既有阈值，避免长距离缓动看起来很卡）。 */
export function shouldJump(distance: number): boolean {
  return shouldJumpInstant(distance);
}