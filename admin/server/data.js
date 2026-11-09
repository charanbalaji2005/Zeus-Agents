// Read/write API over the site's MongoDB (database "Zeus"), the same collections the Python site
// writes: users, cli_tokens, usage, conversations, admin_audit. Nothing here is mocked: with no
// database connected, every route answers 503 and the UI says so.
import { HttpError } from "./auth.js";

const DAY_MS = 86_400_000;
const USER_FIELDS = { _id: 0, email: 1, name: 1, picture: 1, provider: 1, created_at: 1, last_login: 1, last_cli_login: 1, approved: 1 };
const MAX_BULK = 500;

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const clampInt = (v, lo, hi, dflt) => { const n = Number.parseInt(v, 10); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt; };
const isoDaysAgo = (days, now = Date.now()) => new Date(now - days * DAY_MS).toISOString();
const tokensExpr = { $ifNull: ["$usage.total_tokens", { $add: [{ $ifNull: ["$usage.input_tokens", 0] }, { $ifNull: ["$usage.output_tokens", 0] }] }] };

/** Every day in the window, oldest first, so a quiet day is a zero and not a gap. */
export function fillDays(rows, days, now = Date.now()) {
  const byDay = new Map(rows.map((r) => [r._id, r]));
  return Array.from({ length: days }, (_, i) => {
    const day = new Date(now - (days - 1 - i) * DAY_MS).toISOString().slice(0, 10);
    const r = byDay.get(day) || {};
    return { day, requests: r.requests || 0, tokens: r.tokens || 0, input: r.input || 0, output: r.output || 0 };
  });
}

export function dataRoutes(router, { getDb, audit, health }) {
  const db = () => {
    const d = getDb();
    if (!d) throw new HttpError(503, "The database is not connected. Set MONGODB_URI on the server.");
    return d;
  };
  const activeTokenCounts = async (d, emails) => {
    const rows = await d.collection("cli_tokens").aggregate([
      { $match: { email: { $in: emails }, revoked: { $ne: true } } }, { $group: { _id: "$email", n: { $sum: 1 } } },
    ]).toArray();
    return new Map(rows.map((r) => [r._id, r.n]));
  };
  const userExists = async (d, email) => {
    if (!email || !(await d.collection("users").findOne({ email }))) throw new HttpError(404, `No such user: ${email || "(blank)"}.`);
  };
  const revoke = async (d, email) => (await d.collection("cli_tokens").updateMany(
    { email, revoked: { $ne: true } }, { $set: { revoked: true, revoked_at: new Date().toISOString() } })).modifiedCount;

  // ── Overview ──────────────────────────────────────────────────────────────
  router.get("/overview", async (_req, res) => {
    const d = db();
    const since = isoDaysAgo(30);
    const [users, approved, activeTokens, usage30, convo30, tokenSum, daily, models, recentUsers, recentAudit] = await Promise.all([
      d.collection("users").countDocuments({}),
      d.collection("users").countDocuments({ approved: true }),
      d.collection("cli_tokens").countDocuments({ revoked: { $ne: true } }),
      d.collection("usage").countDocuments({ received_at: { $gte: since } }),
      d.collection("conversations").countDocuments({ received_at: { $gte: since } }),
      d.collection("usage").aggregate([{ $match: { received_at: { $gte: since } } }, { $group: { _id: null, t: { $sum: tokensExpr } } }]).toArray(),
      d.collection("usage").aggregate([{ $match: { received_at: { $gte: isoDaysAgo(14) } } },
        { $group: { _id: { $substrBytes: ["$received_at", 0, 10] }, requests: { $sum: 1 }, tokens: { $sum: tokensExpr } } }]).toArray(),
      d.collection("usage").aggregate([{ $match: { received_at: { $gte: since } } },
        { $group: { _id: { $ifNull: ["$model", "unknown"] }, requests: { $sum: 1 } } }, { $sort: { requests: -1 } }, { $limit: 5 }]).toArray(),
      d.collection("users").find({}, { projection: USER_FIELDS }).sort({ created_at: -1 }).limit(6).toArray(),
      d.collection("admin_audit").find({}, { projection: { _id: 0 } }).sort({ at: -1 }).limit(8).toArray(),
    ]);
    res.json({
      counts: { users, approved, pending: users - approved, activeTokens, usage30, conversations30: convo30, tokens30: tokenSum[0]?.t || 0 },
      daily: fillDays(daily, 14),
      models: models.map((m) => ({ name: m._id, requests: m.requests })),
      recentUsers, recentAudit, health: await health(),
    });
  });

  // ── Users & approvals ─────────────────────────────────────────────────────
  router.get("/users", async (req, res) => {
    const d = db();
    const status = String(req.query.status || "all");
    const q = String(req.query.q || "").trim();
    const limit = clampInt(req.query.limit, 1, 100, 25);
    const page = clampInt(req.query.page, 1, 10_000, 1);
    const filter = {};
    if (status === "approved") filter.approved = true;
    if (status === "pending") filter.approved = { $ne: true };
    if (q) filter.$or = [{ email: { $regex: escapeRegex(q), $options: "i" } }, { name: { $regex: escapeRegex(q), $options: "i" } }];
    const [total, docs] = await Promise.all([
      d.collection("users").countDocuments(filter),
      d.collection("users").find(filter, { projection: USER_FIELDS }).sort({ created_at: -1 }).skip((page - 1) * limit).limit(limit).toArray(),
    ]);
    const tokens = await activeTokenCounts(d, docs.map((u) => u.email));
    res.json({ total, page, limit, users: docs.map((u) => ({ ...u, approved: u.approved === true, activeTokens: tokens.get(u.email) || 0 })) });
  });

  router.post("/users/:email/approval", async (req, res) => {
    const d = db();
    const email = req.params.email.toLowerCase();
    await userExists(d, email);
    const approved = req.body?.approved === true;
    await d.collection("users").updateOne({ email }, { $set: { approved, approval_changed_at: new Date().toISOString() } });
    await audit(req, "user.approve", email, { approved });
    res.json({ email, approved });
  });

  router.post("/users/:email/revoke", async (req, res) => {
    const d = db();
    const email = req.params.email.toLowerCase();
    await userExists(d, email);
    const revoked = await revoke(d, email);
    await audit(req, "user.revoke_tokens", email, { revoked });
    res.json({ email, revoked });
  });

  router.delete("/users/:email", async (req, res) => {
    const d = db();
    const email = req.params.email.toLowerCase();
    await userExists(d, email);
    const revoked = await revoke(d, email);
    await d.collection("users").deleteOne({ email });
    let purged = null;
    if (req.query.purge === "true") {
      const [u, c] = await Promise.all([d.collection("usage").deleteMany({ email }), d.collection("conversations").deleteMany({ email })]);
      purged = { usage: u.deletedCount, conversations: c.deletedCount };
    }
    await audit(req, "user.delete", email, { revoked, purged });
    res.json({ email, deleted: true, revoked, purged });
  });

  router.post("/users/bulk", async (req, res) => {
    const d = db();
    const action = String(req.body?.action || "");
    const emails = [...new Set((req.body?.emails || []).map((e) => String(e).toLowerCase()))];
    if (!["approve", "unapprove", "revoke"].includes(action)) throw new HttpError(400, "Action must be approve, unapprove or revoke.");
    if (!emails.length || emails.length > MAX_BULK) throw new HttpError(400, `Select between 1 and ${MAX_BULK} users.`);
    let changed;
    if (action === "revoke") {
      changed = (await d.collection("cli_tokens").updateMany({ email: { $in: emails }, revoked: { $ne: true } },
        { $set: { revoked: true, revoked_at: new Date().toISOString() } })).modifiedCount;
    } else {
      changed = (await d.collection("users").updateMany({ email: { $in: emails } },
        { $set: { approved: action === "approve", approval_changed_at: new Date().toISOString() } })).modifiedCount;
    }
    await audit(req, `user.bulk_${action}`, `${emails.length} users`, { changed });
    res.json({ action, requested: emails.length, changed });
  });

  // ── Usage analytics ───────────────────────────────────────────────────────
  router.get("/usage", async (req, res) => {
    const d = db();
    const days = clampInt(req.query.days, 1, 365, 30);
    const match = { $match: { received_at: { $gte: isoDaysAgo(days) } } };
    const rank = (field) => d.collection("usage").aggregate([match,
      { $group: { _id: { $ifNull: [field, "unknown"] }, requests: { $sum: 1 }, tokens: { $sum: tokensExpr } } },
      { $sort: { requests: -1 } }, { $limit: 10 }]).toArray();
    const [daily, models, providers, users, totals] = await Promise.all([
      d.collection("usage").aggregate([match, { $group: { _id: { $substrBytes: ["$received_at", 0, 10] }, requests: { $sum: 1 }, tokens: { $sum: tokensExpr },
        input: { $sum: { $ifNull: ["$usage.input_tokens", 0] } }, output: { $sum: { $ifNull: ["$usage.output_tokens", 0] } } } }]).toArray(),
      rank("$model"), rank("$provider"), rank("$email"),
      d.collection("usage").aggregate([match, { $group: { _id: null, requests: { $sum: 1 }, tokens: { $sum: tokensExpr },
        input: { $sum: { $ifNull: ["$usage.input_tokens", 0] } }, output: { $sum: { $ifNull: ["$usage.output_tokens", 0] } },
        avgMs: { $avg: { $multiply: [{ $ifNull: ["$api_duration", 0] }, 1000] } }, users: { $addToSet: "$email" } } }]).toArray(),
    ]);
    const t = totals[0] || {};
    const shape = (rows) => rows.map((r) => ({ name: r._id, requests: r.requests, tokens: r.tokens }));
    res.json({ days, daily: fillDays(daily, days),
      totals: { requests: t.requests || 0, tokens: t.tokens || 0, input: t.input || 0, output: t.output || 0, avgMs: Math.round(t.avgMs || 0), users: (t.users || []).length },
      models: shape(models), providers: shape(providers), users: shape(users) });
  });

  // ── Conversations ─────────────────────────────────────────────────────────
  router.get("/conversations", async (req, res) => {
    const d = db();
    const q = String(req.query.q || "").trim();
    const email = String(req.query.email || "").trim().toLowerCase();
    const limit = clampInt(req.query.limit, 1, 100, 25);
    const page = clampInt(req.query.page, 1, 10_000, 1);
    const match = {};
    if (email) match.email = email;
    if (q) match.$or = [{ user_message: { $regex: escapeRegex(q), $options: "i" } }, { assistant_response: { $regex: escapeRegex(q), $options: "i" } }];
    const [result] = await d.collection("conversations").aggregate([
      { $match: match },
      { $group: { _id: { session: "$session_id", email: "$email" }, turns: { $sum: 1 }, first: { $min: "$received_at" }, last: { $max: "$received_at" },
        model: { $last: "$model" }, platform: { $last: "$platform" }, preview: { $first: "$user_message" } } },
      { $sort: { last: -1 } },
      { $facet: { total: [{ $count: "n" }], rows: [{ $skip: (page - 1) * limit }, { $limit: limit }] } },
    ]).toArray();
    res.json({ total: result.total[0]?.n || 0, page, limit, sessions: result.rows.map((r) => ({
      sessionId: r._id.session, email: r._id.email, turns: r.turns, first: r.first, last: r.last, model: r.model, platform: r.platform,
      preview: String(r.preview || "").slice(0, 160) })) });
  });

  router.get("/conversations/:sessionId", async (req, res) => {
    const turns = await db().collection("conversations").find({ session_id: req.params.sessionId }, { projection: { _id: 0 } })
      .sort({ received_at: 1, at: 1 }).limit(500).toArray();
    if (!turns.length) throw new HttpError(404, "No such conversation.");
    res.json({ sessionId: req.params.sessionId, email: turns[0].email, turns });
  });

  router.delete("/conversations/:sessionId", async (req, res) => {
    const { deletedCount } = await db().collection("conversations").deleteMany({ session_id: req.params.sessionId });
    if (!deletedCount) throw new HttpError(404, "No such conversation.");
    await audit(req, "conversation.delete", req.params.sessionId, { turns: deletedCount });
    res.json({ sessionId: req.params.sessionId, deleted: deletedCount });
  });

  // ── Audit log ─────────────────────────────────────────────────────────────
  router.get("/audit", async (req, res) => {
    const d = db();
    const limit = clampInt(req.query.limit, 1, 200, 50);
    const page = clampInt(req.query.page, 1, 10_000, 1);
    const filter = req.query.action ? { action: { $regex: `^${escapeRegex(String(req.query.action))}` } } : {};
    const [total, events] = await Promise.all([
      d.collection("admin_audit").countDocuments(filter),
      d.collection("admin_audit").find(filter, { projection: { _id: 0 } }).sort({ at: -1 }).skip((page - 1) * limit).limit(limit).toArray(),
    ]);
    res.json({ total, page, limit, events });
  });
}
