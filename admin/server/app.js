// Express app factory: `/api/auth/*` (public), every other `/api/*` behind the admin session,
// and the built React console from ../dist for everything else.
import fs from "node:fs";
import path from "node:path";
import express from "express";
import { createAuth, HttpError } from "./auth.js";
import { cliRoutes, runCommand } from "./cli.js";
import { dataRoutes } from "./data.js";

const SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cross-Origin-Opener-Policy": "same-origin",
};

export function createApp({ config, getDb, now = Date.now }) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // Render terminates TLS in front of us; req.ip is the visitor
  app.use((_req, res, next) => { res.set(SECURITY_HEADERS); next(); });
  app.use("/api", express.json({ limit: "64kb" }));
  app.use("/api", (_req, res, next) => { res.set("Cache-Control", "no-store"); next(); });

  const auth = createAuth({ secret: config.adminSecret, secureCookies: config.secureCookies, now });

  async function audit(req, action, target, detail) {
    const d = getDb();
    if (d) await d.collection("admin_audit").insertOne({ at: new Date(now()).toISOString(), action, target, client: req.ip, detail, source: "admin-console" });
  }

  let zeusVersion = { at: 0, value: null };
  async function health() {
    const d = getDb();
    let mongo = { connected: false, latencyMs: null };
    if (d) {
      const t = now();
      try { await d.command({ ping: 1 }); mongo = { connected: true, latencyMs: now() - t }; } catch (err) { mongo = { connected: false, error: err.message }; }
    }
    if (!zeusVersion.value || now() - zeusVersion.at > 10 * 60_000) {
      const r = await runCommand(config, "zeus --version", () => {});
      zeusVersion = { at: now(), value: r.exitCode === 0 ? r.output.split("\n")[0].trim() : null };
    }
    return { mongo, zeus: zeusVersion.value, node: process.version, uptimeS: Math.round(process.uptime()) };
  }

  app.use("/api/auth", auth.router);

  const api = express.Router();
  api.use(auth.requireSession);
  dataRoutes(api, { getDb, audit, health });
  cliRoutes(api, { config, getDb, audit });
  api.get("/system", async (_req, res) => {
    const mem = process.memoryUsage();
    res.json({
      health: await health(),
      memoryMb: Math.round(mem.rss / 1048576),
      settings: {
        MONGODB_URI: Boolean(config.mongoUri), ADMIN_SECRET: Boolean(config.adminSecret), GOOGLE_CLIENT_ID: Boolean(config.googleClientId),
        adminEmails: config.adminEmails, database: config.dbName, repoRoot: path.basename(config.repoRoot), python: config.python,
      },
    });
  });
  app.use("/api", api);
  app.use("/api", () => { throw new HttpError(404, "No such API route."); });

  if (fs.existsSync(path.join(config.distDir, "index.html"))) {
    app.use(express.static(config.distDir, { index: false, maxAge: "1h" }));
    app.get(/^(?!\/api\/).*/, (_req, res) => res.sendFile(path.join(config.distDir, "index.html")));
  }

  // Errors: HttpError carries a safe message; anything else is logged and answered generically.
  app.use((err, _req, res, _next) => {
    const status = err instanceof HttpError ? err.status : err.type === "entity.parse.failed" ? 400 : 500;
    if (status === 500) console.error("[admin]", err);
    if (res.headersSent) return res.end();
    res.status(status).json({ error: status === 500 ? "The admin server hit an error; try again shortly." : err.message, ...(err.extra || {}) });
  });
  return app;
}
