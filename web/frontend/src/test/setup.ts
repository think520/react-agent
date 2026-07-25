import "@testing-library/jest-dom/vitest";

// Sigma checks for WebGL support during module initialization. JSDOM does not
// expose the constructor even when a test never mounts the graph canvas.
Object.defineProperty(globalThis, "WebGL2RenderingContext", {
  configurable: true,
  value: class WebGL2RenderingContext {},
});
Object.defineProperty(globalThis, "WebGLRenderingContext", {
  configurable: true,
  value: class WebGLRenderingContext {},
});
