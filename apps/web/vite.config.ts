import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API runs on :8000; proxying keeps the session cookie same-origin (SameSite=Strict) in development.
const API = process.env.GIGSCOUT_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API, changeOrigin: false },
      "/health": API,
      "/webhooks": API,
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1000, // three.js (~258 kB gzip) is lazy-loaded with the galaxy only
    rollupOptions: {
      output: {
        // Split big vendors into cacheable chunks; three.js only loads with the galaxy.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/](three|@react-three)[\\/]/.test(id)) return "three";
          if (/[\\/](d3|d3-[a-z-]+|internmap|delaunator|robust-predicates)[\\/]/.test(id)) return "d3";
          if (/[\\/]@mantine[\\/]/.test(id)) return "mantine";
          if (/[\\/](react|react-dom|react-router|scheduler)[\\/]/.test(id)) return "react";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
