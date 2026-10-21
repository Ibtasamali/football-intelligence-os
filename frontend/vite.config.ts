import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.FIOS_BACKEND ?? "http://127.0.0.1:8077";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5188,
    strictPort: true,
    host: true,
    proxy: {
      "/api": backend,
      "/health": backend,
      "/ws": { target: backend.replace("http", "ws"), ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 1800 },
});
