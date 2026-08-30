import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local dev (npm run dev), /api is proxied to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
