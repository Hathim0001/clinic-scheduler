import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // The content security policy allows fonts only from the app's own address, so no font may be
  // inlined into the stylesheet as a data: URL (the small font subsets would be otherwise).
  build: { assetsInlineLimit: 0 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/vite-env.d.ts"],
      reporter: ["text-summary", "text"],
      thresholds: { lines: 85, statements: 85, functions: 75, branches: 75 },
    },
  },
});
