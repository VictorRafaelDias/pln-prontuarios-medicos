import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const apiPort = process.env.API_PORT || "8010";
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173, strictPort: false, proxy: { "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true } } },
});
