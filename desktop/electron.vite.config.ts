import path from "node:path";

import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: {
    build: {
      outDir: "dist-electron/main",
    },
  },
  preload: {
    build: {
      outDir: "dist-electron/preload",
    },
  },
  renderer: {
    build: {
      outDir: "dist-electron/renderer",
      rollupOptions: {
        input: path.resolve(__dirname, "src/renderer/index.html"),
      },
    },
    plugins: [react()],
  },
});
