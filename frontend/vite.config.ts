import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API_TARGET: the backend to proxy /api to (default the local one on :8000).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:8000" } },
});
