import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/training-api": {
        target: "http://127.0.0.1:8095",
        changeOrigin: true,
        rewrite: (url) => url.replace(/^\/training-api/, "/api/v1/ml"),
        configure: (proxy) => {
          proxy.on("proxyReq", (request) => {
            try {
              const access = JSON.parse(readFileSync(path.resolve(__dirname,
                "../configuration/federated-training/.local/access.json"), "utf8"));
              request.setHeader("Authorization", `Bearer ${access.token}`);
            } catch {
              request.removeHeader("Authorization");
            }
          });
        },
      },
    },
  },
});
