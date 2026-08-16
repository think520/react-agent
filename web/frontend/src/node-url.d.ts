// Minimal type shim for the Node builtin used by vite.config.ts. @types/node is
// intentionally not installed, so we declare only the one helper we import.
declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}
