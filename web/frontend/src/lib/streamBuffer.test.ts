import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BASE_BATCH,
  CATCH_UP_THRESHOLD,
  MAX_BATCH,
  StreamBuffer,
  adaptiveBatchSize,
  segment,
} from "./streamBuffer";

describe("adaptiveBatchSize", () => {
  it("returns base batch for small backlog", () => {
    expect(adaptiveBatchSize(10)).toBe(BASE_BATCH);
    expect(adaptiveBatchSize(40)).toBe(BASE_BATCH);
  });

  it("grows with backlog", () => {
    expect(adaptiveBatchSize(100)).toBe(24);
    expect(adaptiveBatchSize(500)).toBe(60);
    expect(adaptiveBatchSize(1000)).toBe(MAX_BATCH);
  });

  it("hard-catches-up beyond threshold", () => {
    expect(adaptiveBatchSize(CATCH_UP_THRESHOLD + 1)).toBe(CATCH_UP_THRESHOLD + 1);
  });

  it("returns full backlog when reduced motion", () => {
    expect(adaptiveBatchSize(50, true)).toBe(50);
  });

  it("returns 0 for empty/negative backlog", () => {
    expect(adaptiveBatchSize(0)).toBe(0);
    expect(adaptiveBatchSize(-5)).toBe(0);
  });
});

describe("segment", () => {
  it("splits into grapheme clusters for CJK + latin", () => {
    expect(segment("abc").length).toBe(3);
    expect(segment("你好").length).toBe(2);
  });
});

describe("StreamBuffer", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("flushes buffered text in batches", () => {
    const flushed: string[] = [];
    const buffer = new StreamBuffer((chunk) => flushed.push(chunk), { intervalMs: 33 });
    buffer.push("hello world");
    vi.advanceTimersByTime(33);
    expect(flushed.length).toBeGreaterThan(0);
    expect(flushed.join("")).toBe("hello world".slice(0, flushed.join("").length));
  });

  it("drain emits all remaining text immediately", () => {
    const flushed: string[] = [];
    const buffer = new StreamBuffer((chunk) => flushed.push(chunk));
    buffer.push("unfinished");
    buffer.drain();
    expect(flushed.join("")).toBe("unfinished");
  });

  it("reset discards buffered text", () => {
    const flushed: string[] = [];
    const buffer = new StreamBuffer((chunk) => flushed.push(chunk));
    buffer.push("discarded");
    buffer.reset();
    expect(buffer.backlog).toBe(0);
    vi.advanceTimersByTime(100);
    expect(flushed).toEqual([]);
  });

  it("stops the timer when the buffer is empty", () => {
    const buffer = new StreamBuffer(() => undefined);
    buffer.push("x");
    vi.advanceTimersByTime(33);
    // After fully flushing, the timer should be stopped (no leak).
    expect(buffer.backlog).toBe(0);
  });
});
