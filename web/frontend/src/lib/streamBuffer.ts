/**
 * 30fps streaming buffer + adaptive text throttle (FE-2).
 *
 * SSE deltas are written to a plain JS buffer and flushed to the store in
 * 33ms batches. The batch size adapts to the backlog so a burst from the
 * evidence-gate replay still reads like a typewriter instead of a block, while
 * a huge backlog hard-catches-up. prefers-reduced-motion shows everything.
 */

export const FLUSH_INTERVAL_MS = 33;
export const BASE_BATCH = 4;
export const MAX_BATCH = 200;
export const CATCH_UP_THRESHOLD = 4000;

/** Number of characters to flush for a given backlog length. */
export function adaptiveBatchSize(backlog: number, reducedMotion = false): number {
  if (!Number.isFinite(backlog) || backlog <= 0) return 0;
  if (reducedMotion) return backlog;
  if (backlog > CATCH_UP_THRESHOLD) return backlog; // hard catch-up
  if (backlog > 800) return MAX_BATCH;
  if (backlog > 160) return 60;
  if (backlog > 40) return 24;
  return BASE_BATCH;
}

/** Split text into grapheme clusters (falls back to code points). */
export function segment(text: string): string[] {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return Array.from(segmenter.segment(text), (item) => item.segment);
  }
  return Array.from(text);
}

export interface StreamBufferOptions {
  intervalMs?: number;
  reducedMotion?: boolean;
}

/**
 * Batches incoming text and flushes it on a fixed interval. Use in the chat
 * reducer path instead of flushing per-SSE-event.
 */
export class StreamBuffer {
  private buffer = "";
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly intervalMs: number;
  private readonly reducedMotion: boolean;
  private readonly onFlush: (chunk: string) => void;

  constructor(onFlush: (chunk: string) => void, options: StreamBufferOptions = {}) {
    this.onFlush = onFlush;
    this.intervalMs = options.intervalMs ?? FLUSH_INTERVAL_MS;
    this.reducedMotion = options.reducedMotion ?? false;
  }

  /** Append text and start the flush timer if it is not already running. */
  push(text: string): void {
    if (!text) return;
    this.buffer += text;
    this.start();
  }

  /** Immediately emit all buffered text and stop the timer. */
  drain(): void {
    const remaining = this.buffer;
    this.buffer = "";
    this.stop();
    if (remaining) this.onFlush(remaining);
  }

  /** Discard buffered text and stop the timer. */
  reset(): void {
    this.buffer = "";
    this.stop();
  }

  get backlog(): number {
    return this.buffer.length;
  }

  private start(): void {
    if (this.timer === null) {
      this.timer = setInterval(() => this.step(), this.intervalMs);
    }
  }

  private step(): void {
    if (!this.buffer) {
      this.stop();
      return;
    }
    const batch = adaptiveBatchSize(this.buffer.length, this.reducedMotion);
    const chunk = this.buffer.slice(0, batch);
    this.buffer = this.buffer.slice(batch);
    if (chunk) this.onFlush(chunk);
  }

  private stop(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
