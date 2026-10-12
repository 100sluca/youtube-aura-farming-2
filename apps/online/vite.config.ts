// Page du site en ligne (docs/65) : React + shadcn/ui + Tailwind, construite dans dist/ que le Worker sert.
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  root: "web",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "web/src") } },
  build: { outDir: "../dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
