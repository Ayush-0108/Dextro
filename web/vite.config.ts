import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev: the UI on :5173 forwards /api to the FastAPI server on :8000; build: served by FastAPI itself
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
