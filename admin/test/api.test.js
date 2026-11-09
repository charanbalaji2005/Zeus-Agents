// Behaviour of the admin API against a real MongoDB (mongodb-memory-server) over real HTTP.
// The CLI test runs the real `zeus --version` (ZEUS_PYTHON picks the interpreter that has Zeus).
import assert from "node:assert/strict";
import { after, before, beforeEach, describe, test } from "node:test";
import { MongoClient } from "mongodb";
import { MongoMemoryServer } from "mongodb-memory-server";
import { createApp } from "../server/app.js";
import { loadConfig } from "../server/config.js";

const SECRET = "correct horse battery staple";
let mongod, client, db, server, base;

const day = (offset) => new Date(Date.now() - offset * 86_400_000).toISOString();

async function seed() {
  await db.collection("users").insertMany([
    { email: "ada@example.com", name: "Ada", approved: true, created_at: day(3) },
    { email: "bob@example.com", name: "Bob", approved: false, created_at: day(1) },
  ]);
  await db.collection("cli_tokens").insertMany([
    { email: "ada@example.com", token_sha256: "a", revoked: false },
    { email: "ada@example.com", token_sha256: "b", revoked: true },
  ]);
  await db.collection("usage").insertMany([
    { email: "ada@example.com", model: "claude-opus-5", provider: "anthropic", usage: { input_tokens: 100, output_tokens: 20, total_tokens: 150 }, received_at: day(0) },
    { email: "ada@example.com", model: "claude-opus-5", provider: "anthropic", usage: { input_tokens: 10, output_tokens: 5 }, received_at: day(2) },
    { email: "bob@example.com", model: "gpt-5", provider: "openai-codex", usage: { total_tokens: 40 }, received_at: day(40) },
  ]);
  await db.collection("conversations").insertMany([
    { email: "ada@example.com", session_id: "s1", user_message: "hello zeus", assistant_response: "hi", received_at: day(0) },
    { email: "ada@example.com", session_id: "s1", user_message: "fix the bug", assistant_response: "done", received_at: day(0) },
    { email: "bob@example.com", session_id: "s2", user_message: "deploy please", assistant_response: "ok", received_at: day(1) },
  ]);
}

async function call(path, { method = "GET", body, cookie, header = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (cookie) headers.Cookie = cookie;
  if (header && method !== "GET") headers["X-Zeus-Admin"] = "1";
  const res = await fetch(base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* event stream or empty */ }
  return { status: res.status, json, text, cookie: res.headers.get("set-cookie") };
}

async function signIn() {
  const r = await call("/api/auth/login", { method: "POST", body: { secret: SECRET } });
  assert.equal(r.status, 200);
  return r.cookie.split(";")[0];
}

function start(secret) {
  const config = { ...loadConfig({}), adminSecret: secret, secureCookies: false, python: process.env.ZEUS_PYTHON || "python" };
  server = createApp({ config, getDb: () => db }).listen(0, "127.0.0.1");
  base = `http://127.0.0.1:${server.address().port}`;
}

before(async () => {
  mongod = await MongoMemoryServer.create();
  client = await MongoClient.connect(mongod.getUri());
});
after(async () => { await client?.close(); await mongod?.stop(); });
beforeEach(async () => {
  server?.close();
  db = client.db(`zeus_test_${Math.random().toString(36).slice(2)}`);
  await seed();
  start(SECRET);
});

describe("sign-in", () => {
  test("without ADMIN_SECRET the console is locked", async () => {
    server.close();
    start("");
    assert.equal((await call("/api/auth/me")).json.enabled, false);
    assert.equal((await call("/api/auth/login", { method: "POST", body: { secret: "" } })).status, 503);
    assert.equal((await call("/api/overview")).status, 503);
  });

  test("wrong password is refused; the right one gives an HttpOnly session", async () => {
    assert.equal((await call("/api/auth/login", { method: "POST", body: { secret: "guess" } })).status, 401);
    const ok = await call("/api/auth/login", { method: "POST", body: { secret: SECRET } });
    assert.equal(ok.status, 200);
    assert.match(ok.cookie, /HttpOnly/);
    assert.match(ok.cookie, /SameSite=Strict/);
    assert.equal((await call("/api/overview")).status, 401);
    assert.equal((await call("/api/overview", { cookie: ok.cookie.split(";")[0] })).status, 200);
  });

  test("repeated wrong passwords lock the client out", async () => {
    for (let i = 0; i < 10; i++) await call("/api/auth/login", { method: "POST", body: { secret: "nope" } });
    assert.equal((await call("/api/auth/login", { method: "POST", body: { secret: SECRET } })).status, 429);
  });

  test("a forged cookie is rejected", async () => {
    const forged = `zeus_admin=${Date.now() + 3_600_000}.not-a-signature`;
    assert.equal((await call("/api/overview", { cookie: forged })).status, 401);
  });

  test("writes need the admin request header", async () => {
    const cookie = await signIn();
    const r = await call("/api/users/bob@example.com/approval", { method: "POST", body: { approved: true }, cookie, header: false });
    assert.equal(r.status, 403);
    assert.equal((await db.collection("users").findOne({ email: "bob@example.com" })).approved, false);
  });
});

describe("data", () => {
  test("overview counts come from the database", async () => {
    const { json } = await call("/api/overview", { cookie: await signIn() });
    assert.deepEqual({ ...json.counts }, { users: 2, approved: 1, pending: 1, activeTokens: 1, usage30: 2, conversations30: 3, tokens30: 165 });
    assert.equal(json.daily.length, 14);
    assert.equal(json.daily.at(-1).requests, 1);
    assert.equal(json.health.mongo.connected, true);
  });

  test("approving a user updates MongoDB and is audited", async () => {
    const cookie = await signIn();
    const pending = await call("/api/users?status=pending", { cookie });
    assert.deepEqual(pending.json.users.map((u) => u.email), ["bob@example.com"]);
    assert.equal((await call("/api/users/bob@example.com/approval", { method: "POST", body: { approved: true }, cookie })).status, 200);
    assert.equal((await db.collection("users").findOne({ email: "bob@example.com" })).approved, true);
    const event = await db.collection("admin_audit").findOne({ action: "user.approve" });
    assert.equal(event.target, "bob@example.com");
    assert.equal((await call("/api/users/nobody@example.com/approval", { method: "POST", body: { approved: true }, cookie })).status, 404);
  });

  test("delete with purge removes the account's tokens, usage and conversations", async () => {
    const cookie = await signIn();
    const r = await call("/api/users/ada@example.com?purge=true", { method: "DELETE", cookie });
    assert.equal(r.status, 200);
    assert.deepEqual(r.json.purged, { usage: 2, conversations: 2 });
    assert.equal(await db.collection("users").countDocuments({ email: "ada@example.com" }), 0);
    assert.equal(await db.collection("cli_tokens").countDocuments({ email: "ada@example.com", revoked: false }), 0);
  });

  test("bulk revoke cuts off every terminal of the selected users", async () => {
    const r = await call("/api/users/bulk", { method: "POST", body: { action: "revoke", emails: ["ada@example.com"] }, cookie: await signIn() });
    assert.equal(r.json.changed, 1);
    assert.equal(await db.collection("cli_tokens").countDocuments({ revoked: false }), 0);
  });

  test("usage analytics respect the window and count tokens without total_tokens", async () => {
    const { json } = await call("/api/usage?days=30", { cookie: await signIn() });
    assert.equal(json.totals.requests, 2);
    assert.equal(json.totals.tokens, 165);
    assert.deepEqual(json.models, [{ name: "claude-opus-5", requests: 2, tokens: 165 }]);
    assert.equal(json.daily.length, 30);
  });

  test("conversations group by session and open in order", async () => {
    const cookie = await signIn();
    const list = await call("/api/conversations", { cookie });
    assert.equal(list.json.total, 2);
    assert.equal(list.json.sessions.find((s) => s.sessionId === "s1").turns, 2);
    assert.equal((await call("/api/conversations?q=deploy", { cookie })).json.sessions[0].sessionId, "s2");
    const detail = await call("/api/conversations/s1", { cookie });
    assert.deepEqual(detail.json.turns.map((t) => t.user_message), ["hello zeus", "fix the bug"]);
  });
});

describe("cli", () => {
  test("only allowlisted commands run", async () => {
    const r = await call("/api/cli/run", { method: "POST", body: { command: "zeus config set x y" }, cookie: await signIn() });
    assert.equal(r.status, 400);
  });

  test("a real command streams its output and is recorded", { timeout: 120_000 }, async () => {
    const r = await call("/api/cli/run", { method: "POST", body: { command: "zeus --version" }, cookie: await signIn() });
    assert.equal(r.status, 200);
    const events = r.text.trim().split("\n\n").map((block) => {
      const [e, d] = block.split("\n");
      return { event: e.slice(7), data: JSON.parse(d.slice(6)) };
    });
    assert.equal(events[0].event, "start");
    assert.match(events.filter((e) => e.event === "output").map((e) => e.data.text).join(""), /Zeus Agents/);
    assert.equal(events.at(-1).event, "end");
    assert.equal(events.at(-1).data.exitCode, 0);
    const stored = await db.collection("admin_cli_runs").findOne({ command: "zeus --version" });
    assert.equal(stored.exit_code, 0);
  });
});
