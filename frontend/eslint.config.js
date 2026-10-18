import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: { ...reactHooks.configs.recommended.rules },
  },
  {
    files: ["*.config.{js,ts}"],
    languageOptions: { globals: globals.node },
  },
  {
    // End-to-end checks run in Node but pass functions to the browser (page.evaluate), where
    // `document` and the injected `axe` exist.
    files: ["e2e/**/*.mjs"],
    languageOptions: { globals: { ...globals.node, ...globals.browser, axe: "readonly" } },
  },
);
