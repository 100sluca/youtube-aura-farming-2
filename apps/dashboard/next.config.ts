import type { NextConfig } from "next";
import path from "node:path";

// Le monorepo contient d'autres package.json / next.config au-dessus de cette app :
// on fixe explicitement la racine pour Turbopack et le tracing des fichiers.
const appRoot = path.join(process.cwd());

// Version de production servie au quotidien par launcher/dashboard.ps1 (docs/56-dashboard-rapide.md) : construite dans
// .next-live/a ou .next-live/b pendant que l'autre dossier continue de servir. Son propre tsconfig (copie ignorée par
// git), sinon Next ajouterait ce dossier aux « include » de tsconfig.json. Pas de contrôle des types, comme next dev :
// la CI s'en charge, et une faute de type d'une session en cours ne bloque pas la mise à jour.
const liveDir = process.env.YT2_DIST_DIR;

const nextConfig: NextConfig = {
  turbopack: {
    root: appRoot,
  },
  outputFileTracingRoot: appRoot,
  ...(liveDir ? { distDir: liveDir, typescript: { tsconfigPath: "tsconfig.live.json", ignoreBuildErrors: true } } : {}),
};

export default nextConfig;
