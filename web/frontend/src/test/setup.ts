import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// CI runners are slower than a dev machine. The app shell test failed there
// with "Unable to find role=heading" because a lazily-loaded route chunk can
// take longer than the 1s default. Those assertions mean "eventually
// rendered", not "rendered within one second", so raise the default wait
// instead of sprinkling timeouts through individual tests.
configure({ asyncUtilTimeout: 5000 });

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
