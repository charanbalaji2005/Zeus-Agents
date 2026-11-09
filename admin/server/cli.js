// The admin CLI page: runs the server's real `zeus` for an allowlisted set of read-only
// diagnostics and streams stdout/stderr to the browser as Server-Sent Events while it runs.
// Nothing else can be executed: no shell, no arguments from the client, a time limit per command,
// at most two runs at once, and the server's own secrets removed from the child's environment.
import { spawn } from "node:child_process";
import { ObjectId } from "mongodb";
import { HttpError } from "./auth.js";

export const COMMANDS = {
  "zeus --version": { args: ["--version"], timeoutS: 30, group: "System", description: "Installed Zeus version, Python and SDK versions." },
  "zeus status --full": { args: ["status", "--full"], timeoutS: 90, group: "System", description: "Every component's configuration and health." },
  "zeus doctor": { args: ["doctor"], timeoutS: 150, group: "Diagnostics", description: "Full health check: environment, packages, providers, tools." },
  "zeus tools list": { args: ["tools", "list"], timeoutS: 45, group: "Tools", description: "Toolsets and whether each is enabled." },
  "zeus skills list": { args: ["skills", "list"], timeoutS: 45, group: "Tools", description: "Installed skills." },
  "zeus plugins list": { args: ["plugins", "list"], timeoutS: 45, group: "Tools", description: "Installed plugins and their state." },
  "zeus auth list": { args: ["auth", "list"], timeoutS: 30, group: "Accounts", description: "Provider credentials configured on this server (values hidden)." },
  "zeus cron list": { args: ["cron", "list"], timeoutS: 30, group: "Automation", description: "Scheduled jobs on this server." },
};

const SCRUBBED_ENV = ["MONGODB_URI", "ADMIN_SECRET", "GITHUB_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"];
const MAX_CONCURRENT = 2;
const MAX_STORED_OUTPUT = 200_000;

function childEnv() {
  const env = { ...process.env };
  for (const name of SCRUBBED_ENV) delete env[name];
  return { ...env, PYTHONIOENCODING: "utf-8", NO_COLOR: "1", TERM: "dumb", COLUMNS: "120" };
}

/** Run one allowlisted command; `onChunk(stream, text)` sees output as it arrives. */
export function runCommand({ python, repoRoot }, command, onChunk, { signal } = {}) {
  const spec = COMMANDS[command];
  const started = Date.now();
  return new Promise((resolve) => {
    let output = "";
    let timedOut = false;
    let settled = false;
    const child = spawn(python, ["-m", "zeus_cli.main", ...spec.args], {
      cwd: repoRoot, env: childEnv(), stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
    });
    const finish = (exitCode, error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", stop);
      resolve({ exitCode, timedOut, error, durationMs: Date.now() - started, output });
    };
    const stop = () => child.kill("SIGKILL");
    const timer = setTimeout(() => { timedOut = true; stop(); }, spec.timeoutS * 1000);
    signal?.addEventListener("abort", stop, { once: true });
    for (const stream of ["stdout", "stderr"]) {
      child[stream].setEncoding("utf8");
      child[stream].on("data", (text) => {
        if (output.length < MAX_STORED_OUTPUT) output += text;
        onChunk(stream, text);
      });
    }
    child.on("error", (err) => finish(null, `Could not start ${python}: ${err.message}`));
    child.on("close", (code) => finish(code, null));
  });
}

export function cliRoutes(router, { config, getDb, audit }) {
  let running = 0;

  router.get("/cli/commands", (_req, res) => {
    res.json({ commands: Object.entries(COMMANDS).map(([command, s]) => ({ command, group: s.group, description: s.description, timeoutS: s.timeoutS })) });
  });

  router.get("/cli/history", async (_req, res) => {
    const db = getDb();
    if (!db) return res.json({ runs: [] });
    const runs = await db.collection("admin_cli_runs").find({}, { projection: { output: 0 } }).sort({ started_at: -1 }).limit(30).toArray();
    res.json({ runs: runs.map(({ _id, ...r }) => ({ id: String(_id), ...r })) });
  });

  router.get("/cli/history/:id", async (req, res) => {
    const db = getDb();
    if (!db || !ObjectId.isValid(req.params.id)) throw new HttpError(404, "No such run.");
    const run = await db.collection("admin_cli_runs").findOne({ _id: new ObjectId(req.params.id) });
    if (!run) throw new HttpError(404, "No such run.");
    const { _id, ...rest } = run;
    res.json({ id: String(_id), ...rest });
  });

  router.post("/cli/run", async (req, res) => {
    const command = String(req.body?.command || "").split(/\s+/).filter(Boolean).join(" ");
    if (!COMMANDS[command]) throw new HttpError(400, `Not an allowed command. Allowed: ${Object.keys(COMMANDS).join(", ")}`);
    if (running >= MAX_CONCURRENT) throw new HttpError(429, "Two commands are already running; wait for one to finish.");
    running += 1;
    res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", Connection: "keep-alive" });
    const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    const abort = new AbortController();
    res.on("close", () => { if (!res.writableFinished) abort.abort(); });
    const startedAt = new Date().toISOString();
    send("start", { command, startedAt, timeoutS: COMMANDS[command].timeoutS });
    try {
      const result = await runCommand(config, command, (stream, text) => send("output", { stream, text }), { signal: abort.signal });
      const summary = { exitCode: result.exitCode, timedOut: result.timedOut, durationMs: result.durationMs, error: result.error };
      const db = getDb();
      if (db) {
        await db.collection("admin_cli_runs").insertOne({ command, started_at: startedAt, client: req.ip, exit_code: result.exitCode,
          timed_out: result.timedOut, duration_ms: result.durationMs, error: result.error, output: result.output });
      }
      await audit(req, "console.exec", command, { exit_code: result.exitCode, timed_out: result.timedOut });
      send("end", summary);
    } finally {
      running -= 1;
      res.end();
    }
  });
}
