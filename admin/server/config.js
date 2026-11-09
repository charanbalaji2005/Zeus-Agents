// Runtime settings, read once at start. Secrets come only from the environment (Render dashboard).
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export function loadConfig(env = process.env) {
  return {
    port: Number(env.PORT || 3100),
    mongoUri: env.MONGODB_URI || "",
    dbName: env.MONGODB_DB || "Zeus",
    adminSecret: env.ADMIN_SECRET || "",
    adminEmails: (env.ADMIN_EMAILS || "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean),
    googleClientId: env.GOOGLE_CLIENT_ID || "",
    // The checkout whose `zeus` the CLI page runs: this repository by default.
    repoRoot: env.ZEUS_REPO_ROOT || path.resolve(here, "..", ".."),
    python: env.ZEUS_PYTHON || (process.platform === "win32" ? "python" : "python3"),
    // Secure cookies everywhere except plain-http local development.
    secureCookies: env.NODE_ENV === "production" || Boolean(env.RENDER),
    distDir: path.resolve(here, "..", "dist"),
  };
}
