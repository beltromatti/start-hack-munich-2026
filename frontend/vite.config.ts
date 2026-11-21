import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API_TARGET: the backend to proxy /api to (default the local one on :8000).
export default defineConfig({
  plugins: [react()],
  // two pages: the sessions UI at / and the CRM at /crm.html
  build: { rollupOptions: { input: { main: "index.html", crm: "crm.html" } } },
  server: { port: 5173, proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:8000" } },
});
