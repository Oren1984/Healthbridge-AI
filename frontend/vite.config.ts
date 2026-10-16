import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies the API (run the Docker stack, which proxies the API to the backend on :8003).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.HB_API_URL ?? "http://localhost:8083", ws: true, changeOrigin: false } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
});
