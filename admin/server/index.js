// Entry point: connect MongoDB (retrying in the background), then serve the admin console.
import { MongoClient } from "mongodb";
import { createApp } from "./app.js";
import { loadConfig } from "./config.js";

const config = loadConfig();
let db = null;

async function ensureIndexes(d) {
  await Promise.all([
    d.collection("admin_audit").createIndex({ at: -1 }),
    d.collection("admin_cli_runs").createIndex({ started_at: -1 }),
    d.collection("usage").createIndex({ received_at: -1 }),
    d.collection("conversations").createIndex({ session_id: 1, received_at: 1 }),
  ]);
}

async function connect() {
  if (!config.mongoUri) {
    console.warn("[admin] MONGODB_URI is not set: data pages will report that the database is not connected.");
    return;
  }
  try {
    const client = new MongoClient(config.mongoUri, { serverSelectionTimeoutMS: 5000 });
    await client.connect();
    const d = client.db(config.dbName);
    await ensureIndexes(d);
    db = d;
    console.log(`[admin] Connected to MongoDB database "${config.dbName}".`);
  } catch (err) {
    console.error(`[admin] MongoDB connection failed (${err.message}); retrying in 30s.`);
    setTimeout(connect, 30_000);
  }
}

if (!config.adminSecret) console.warn("[admin] ADMIN_SECRET is not set: the console stays locked until it is.");
connect();
createApp({ config, getDb: () => db }).listen(config.port, "0.0.0.0", () => {
  console.log(`[admin] Zeus admin console on http://0.0.0.0:${config.port}`);
});
