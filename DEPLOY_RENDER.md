# Deploying Zeus CLI Server & Web Terminal to Render

Deploy the **Zeus CLI Server**, **Interactive Web Terminal (`/cli`)**, **Marketing Landing Page**, and **Admin Control Plane (`/admin`)** to **Render** ([https://render.com](https://render.com)) with **Google OAuth 2.0**, **GitHub Login**, and **MongoDB Atlas** persistence.

---

## 1. Quick Deploy via Render Blueprint (Recommended)

1. Push your repository to **GitHub**:
   ```bash
   git push origin main
   ```
2. Go to your [Render Dashboard](https://dashboard.render.com/) &rarr; **New +** &rarr; **Blueprint**.
3. Select your repository `charanbalaji2005/Zeus-Agents`.
4. Render will automatically detect [`render.yaml`](./render.yaml) configured with:
   - **Service Name**: `zeus-cli-server`
   - **Dockerfile Path**: `./Dockerfile.cli`
   - **Port**: `10000`
5. In the environment variables prompt, provide your configuration:
   ```
   MONGODB_URI=mongodb+srv://<db-user>:<db-password>@cluster0.abcde.mongodb.net/Zeus?retryWrites=true&w=majority
   ADMIN_SECRET=your-secure-admin-passphrase-here
   ```
6. Click **Apply**. Render will build and launch the service with port 10000 open immediately!

---

## 2. Fixing "No open ports detected" on an Existing Render Service

If your Render deployment previously timed out with:
```
==> No open ports detected, continuing to scan...
==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
```
This occurred because Render defaulted to building the root `Dockerfile` whose entrypoint ran an interactive CLI REPL waiting on stdin rather than a web server.

### Fix in 2 clicks:
1. In your Render Dashboard, select your service &rarr; **Settings** &rarr; **Build & Deploy**.
2. Set **Dockerfile Path**: `./Dockerfile.cli` (or `./Dockerfile.landing`).
3. Set **Docker Build Context Directory**: `.`.
4. Set **Health Check Path**: `/health`.
5. Under **Environment Variables**, ensure:
   - `PORT` = `10000`
   - `RENDER` = `true`
   - `ADMIN_SECRET` = `<your-secure-passphrase>`
6. Click **Manual Deploy** &rarr; **Deploy latest commit**.
7. Render's port scanner will immediately detect the open port `10000` and report `Your service is live 🎉`.

---

## 3. Endpoints & Features

| Route | Description |
| :--- | :--- |
| `/` | Zeus Agents official marketing page with App Coming Soon badges, full CLI installation instructions, and Pricing Announcements. |
| `/docs` | Dedicated full-page documentation covering Linux, macOS, and Windows installation, configuration, and architecture. |
| `/admin` | **Zeus Control Plane**: Secure admin panel to monitor server health, approve users, inspect toolsets, and review live logs. |
| `/cli` or `/terminal` | **Interactive Retro-Brutalist Web Terminal** allowing users to run `zeus status`, `zeus tools list`, `zeus auth list`, `zeus --version`, `zeus doctor`, etc. directly inside any web browser. |
| `/api/cli/run` | Safe backend API executing Zeus CLI subcommands with JSON responses and 30s timeout guards. |
| `/health` | Health check endpoint returning `{ "status": "ok", "service": "zeus-cli-server", "port": 10000 }`. |
| `/api/auth/token` | Generates unique live CLI authentication tokens for terminal login. |
| `/api/auth/google` | Next Auth & Google OAuth 2.0 credential verification with MongoDB Atlas persistence (`Zeus.users`). |

---

## 4. Whitelist Render URL in Google Cloud & MongoDB Atlas

1. **Google Cloud Console**:
   - Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
   - Under **Authorized JavaScript origins**, add your Render URL: `https://<your-service>.onrender.com`.
   - Under **Authorized redirect URIs**, add `https://<your-service>.onrender.com` and `https://<your-service>.onrender.com/`.
2. **MongoDB Atlas**:
   - In MongoDB Atlas, go to **Network Access** &rarr; **IP Access List**.
   - Add `0.0.0.0/0` (Allow access from anywhere) so Render's cloud servers can connect to your database.

---

## 5. Deploying & Accessing the Admin Panel (`/admin`)

The Zeus Admin Control Plane (`/admin`) gives you full administrative command over your deployed Zeus instance without requiring SSH access.

### Step 1: Configure `ADMIN_SECRET` on Render
1. Open your [Render Dashboard](https://dashboard.render.com/) and navigate to your `zeus-cli-server` web service.
2. Click **Environment** in the left sidebar.
3. Click **Add Environment Variable**:
   - **Key**: `ADMIN_SECRET`
   - **Value**: Choose a strong, secret passphrase (e.g. `zeus-master-key-2026!`).
4. Click **Save Changes**. Render will automatically redeploy the service with the admin secret active.

> [!IMPORTANT]
> If `ADMIN_SECRET` is unset, all `/api/admin/*` endpoints return `503 Service Unavailable` for security to prevent unauthorized access.

### Step 2: Open and Authenticate
1. Navigate to:
   ```
   https://<your-service>.onrender.com/admin
   ```
2. You will see the **Zeus Control Plane Lock Screen**.
3. Enter the passphrase you configured in `ADMIN_SECRET` and click **Unlock Dashboard**.
4. The key is securely stored in your browser session and sent via HMAC-checked `X-Admin-Secret` headers on all administrative API requests.

### Step 3: Admin Features Available
- **Telemetry & Health**: Real-time MongoDB Atlas ping latency, active LLM model provider, server uptime, and SQLite cache stats.
- **User Database & Waitlist**: View all registered users from MongoDB (`Zeus.users`), toggle priority beta approvals, regenerate or revoke terminal CLI tokens, and delete accounts.
- **Toolsets & MCP**: Inspect enabled/disabled built-in toolsets (terminal, web, memory, skills) and connected Model Context Protocol servers.
- **Live Server Logs**: View real-time HTTP requests, authentication audits, and server error feeds in a 200-entry ring buffer.
- **Command Sandbox**: Execute allowlisted administrative CLI diagnostics (`zeus status --full`, `zeus doctor`, `zeus auth list`, `zeus cron list`, `zeus tools list`, `zeus --version`) with environment secrets scrubbed.
