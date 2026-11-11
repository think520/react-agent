import { afterEach, describe, expect, it } from "vitest";

import { shouldIgnoreShortcut } from "./ime";

function press(target: Element, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key: "[", bubbles: true, ...init });
  Object.defineProperty(event, "target", { value: target });
  return event;
}

afterEach(() => { document.body.innerHTML = ""; });

describe("shouldIgnoreShortcut", () => {
  it("lets shortcuts through on the page body", () => {
    expect(shouldIgnoreShortcut(press(document.body))).toBe(false);
  });

  it("ignores keys typed into text fields, textareas and editable content", () => {
    document.body.innerHTML = `<input id="t" type="search" /><textarea id="a"></textarea><div id="e" contenteditable="true"></div>`;
    expect(shouldIgnoreShortcut(press(document.getElementById("t")!))).toBe(true);
    expect(shouldIgnoreShortcut(press(document.getElementById("a")!))).toBe(true);
    const editable = document.getElementById("e")!;
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(shouldIgnoreShortcut(press(editable))).toBe(true);
  });

  it("keeps shortcuts on non-text inputs such as checkboxes", () => {
    document.body.innerHTML = `<input id="c" type="checkbox" />`;
    expect(shouldIgnoreShortcut(press(document.getElementById("c")!))).toBe(false);
  });

  it("ignores keys while an IME is composing", () => {
    expect(shouldIgnoreShortcut(press(document.body, { isComposing: true }))).toBe(true);
  });

  it("ignores keys inside an open dialog", () => {
    document.body.innerHTML = `<div role="dialog"><button id="b">x</button></div>`;
    expect(shouldIgnoreShortcut(press(document.getElementById("b")!))).toBe(true);
  });
});
