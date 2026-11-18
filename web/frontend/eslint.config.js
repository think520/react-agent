import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "test-results/**", "playwright-report/**"],
  },
  {
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}", "e2e/**/*.ts", "vite.config.ts", "playwright.config.ts"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      globals: { ...globals.browser, ...globals.es2022 },
    },
    rules: {
      // Allow intentionally unused args/vars prefixed with _ (common for handlers).
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [reactHooks.configs.flat.recommended],
    rules: {
      // Data-loading effects across the app call setState after awaiting the
      // API; rewriting them for this new react-hooks v7 rule would be a large
      // behavioral refactor with no user-facing benefit. Revisit per-page.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
      "src/**/__tests__/**",
      "src/lib/api/**",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch']",
          message: "Use the API facade from src/lib/api; direct fetch is only allowed in src/lib/api.",
        },
        {
          selector: "CallExpression[callee.property.name='fetch']",
          message: "Use the API facade from src/lib/api; direct fetch is only allowed in src/lib/api.",
        },
      ],
    },
  },
  {
    files: ["e2e/**/*.ts"],
    rules: {
      // Playwright specs build loose mock payloads; strict typing adds noise.
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
