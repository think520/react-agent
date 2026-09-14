// Minimal type shims for the Node builtins this package touches outside the
// browser bundle: vite.config.ts and the design-token contract test.
// @types/node is intentionally not installed, so declare only what we import.
declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}

declare module "node:path" {
  export function resolve(...parts: string[]): string;
}

declare module "node:fs" {
  export function existsSync(path: string): boolean;
  export function readFileSync(path: string, encoding: "utf8"): string;
}

declare const process: { cwd(): string };
