import type { NextConfig } from "next";
import path from "node:path";

// Le monorepo contient d'autres package.json / next.config au-dessus de cette app :
// on fixe explicitement la racine pour Turbopack et le tracing des fichiers.
const appRoot = path.join(process.cwd());

const nextConfig: NextConfig = {
  turbopack: {
    root: appRoot,
  },
  outputFileTracingRoot: appRoot,
};

export default nextConfig;
