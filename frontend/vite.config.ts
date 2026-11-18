import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    // La suite Playwright in `e2e/` non gira sotto vitest.
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json-summary"],
      include: ["src/lib/**/*.ts", "src/api/**/*.ts", "src/hooks/**/*.ts"],
      exclude: ["src/api/schema.d.ts", "**/*.test.ts", "**/*.test.tsx"],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
});
