// Admin sign-in: one shared ADMIN_SECRET, exchanged for a signed, HttpOnly session cookie.
// No default secret: without ADMIN_SECRET every admin route answers 503. Rotating the secret
// invalidates every session, because the cookie signing key is derived from it.
import crypto from "node:crypto";
import express from "express";

export const COOKIE = "zeus_admin";
const SESSION_MS = 12 * 3600_000;
const MAX_FAILURES = 10;
const LOCKOUT_MS = 15 * 60_000;

export class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

function digest(value) {
  return crypto.createHash("sha256").update(String(value)).digest();
}

function readCookie(header, name) {
  for (const part of (header || "").split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

export function createAuth({ secret, secureCookies, now = Date.now }) {
  const failures = new Map();
  const key = secret ? crypto.createHmac("sha256", secret).update("zeus-admin-session").digest() : null;
  const sign = (exp) => crypto.createHmac("sha256", key).update(String(exp)).digest("base64url");

  function sessionValid(raw) {
    if (!key || !raw) return false;
    const [exp, sig] = raw.split(".");
    if (!exp || !sig || !(Number(exp) > now())) return false;
    const want = Buffer.from(sign(exp));
    const got = Buffer.from(sig);
    return got.length === want.length && crypto.timingSafeEqual(got, want);
  }

  function lockedOut(client) {
    const recent = (failures.get(client) || []).filter((t) => now() - t < LOCKOUT_MS);
    failures.set(client, recent);
    return recent.length >= MAX_FAILURES;
  }

  function cookie(value, maxAgeMs) {
    const attrs = [`${COOKIE}=${value}`, "Path=/", "HttpOnly", "SameSite=Strict", `Max-Age=${Math.floor(maxAgeMs / 1000)}`];
    if (secureCookies) attrs.push("Secure");
    return attrs.join("; ");
  }

  const router = express.Router();

  router.post("/login", (req, res) => {
    if (!key) throw new HttpError(503, "The admin console is disabled: set ADMIN_SECRET on the server.");
    const client = req.ip || "unknown";
    if (lockedOut(client)) throw new HttpError(429, "Too many wrong attempts. Try again in 15 minutes.");
    const given = String(req.body?.secret ?? "");
    if (!given || !crypto.timingSafeEqual(digest(given), digest(secret))) {
      failures.get(client).push(now());
      throw new HttpError(401, "Wrong admin password.");
    }
    failures.delete(client);
    const exp = now() + SESSION_MS;
    res.setHeader("Set-Cookie", cookie(`${exp}.${sign(exp)}`, SESSION_MS));
    res.json({ signedIn: true, expiresAt: new Date(exp).toISOString() });
  });

  router.post("/logout", (_req, res) => {
    res.setHeader("Set-Cookie", cookie("", 0));
    res.json({ signedIn: false });
  });

  router.get("/me", (req, res) => {
    res.json({ enabled: Boolean(key), signedIn: sessionValid(readCookie(req.headers.cookie, COOKIE)) });
  });

  // Every other /api route: a valid session, and on writes the custom header a cross-site form
  // cannot send (SameSite=Strict already blocks the cookie; this is defense in depth).
  function requireSession(req, _res, next) {
    if (!key) return next(new HttpError(503, "The admin console is disabled: set ADMIN_SECRET on the server."));
    if (!sessionValid(readCookie(req.headers.cookie, COOKIE))) return next(new HttpError(401, "Sign in to continue."));
    if (req.method !== "GET" && req.get("X-Zeus-Admin") !== "1") return next(new HttpError(403, "Missing admin request header."));
    next();
  }

  return { router, requireSession };
}
