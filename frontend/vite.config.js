import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  base: mode === "github-pages"
    ? "/Gujarat-Police-Innovation-Hackathon-2026_sol_1/"
    : "/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ai": "http://127.0.0.1:8000",
      "/alerts": "http://127.0.0.1:8000",
      "/analytics": "http://127.0.0.1:8000",
      "/cameras": "http://127.0.0.1:8000",
      "/detections": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/stats": "http://127.0.0.1:8000",
      "/vehicles": "http://127.0.0.1:8000",
      "/watchlist": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
}));
