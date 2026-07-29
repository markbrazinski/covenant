/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Record build — single entry (index.html → src/record/main.tsx).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: "node", include: ["src/**/*.test.ts"] }
});
