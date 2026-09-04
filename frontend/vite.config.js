import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Same-origin development calls: Vite forwards /api to FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
