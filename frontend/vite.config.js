import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  server: {
    host: '0.0.0.0',
    proxy: {
      // 프론트에서 "/api"로 시작하는 요청을 백엔드로 프록시
      "/api": {
        target: "http://127.0.0.1:5001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""), // '/api/xxx' → '/xxx'
      },
    },
  },
});
