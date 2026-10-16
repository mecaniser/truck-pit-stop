import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5186,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8006" },
  },
  build: { outDir: "../../dist-communications", emptyOutDir: true },
});
