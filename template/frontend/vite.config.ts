import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

import pkg from "./package.json"

// https://vitejs.dev/config/
export default defineConfig({
  // Keelstone: the backend does not serve the frontend; it is built to dist/ and served by its
  // own container (frontend/Dockerfile). Port 3000 is the origin the backend allows by default
  // (CORS_ORIGINS, FRONTEND_URL).
  // Keelstone: the version shown in the sidebar, from package.json, which scripts/version.py
  // keeps equal to VERSION at the root of the project.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 3000,
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
})
