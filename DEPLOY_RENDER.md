# Deploying Zeus CLI Server & Web Terminal to Render

Deploy the **Zeus CLI Server**, **Interactive Web Terminal (`/cli`)**, and **Marketing Landing Page** to **Render** ([https://render.com](https://render.com)) with **Google OAuth 2.0**, **GitHub Login**, and **MongoDB Atlas** persistence.

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
5. In the environment variables prompt, optionally provide `MONGODB_URI`:
   ```
   MONGODB_URI=mongodb+srv://<db-user>:<db-password>@cluster0.abcde.mongodb.net/Zeus?retryWrites=true&w=majority
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
6. Click **Manual Deploy** &rarr; **Deploy latest commit**.
7. Render's port scanner will immediately detect the open port `10000` and report `Your service is live 🎉`.

---

## 3. Endpoints & Features

| Route | Description |
| :--- | :--- |
| `/` | Zeus Agents official marketing page with App Coming Soon badges, full CLI installation instructions, and Pricing Announcements. |
| `/cli` or `/terminal` | **Interactive Retro-Brutalist Web Terminal** allowing users to run `zeus status`, `zeus tools list`, `zeus auth list`, `zeus --version`, `zeus doctor`, etc. directly inside any web browser. |
| `/api/cli/run` | Safe backend API executing Zeus CLI subcommands with JSON responses and 30s timeout guards. |
| `/health` | Health check endpoint returning `{ "status": "ok", "service": "zeus-cli-server", "port": 10000 }`. |
| `/api/auth/token` | Generates unique live CLI authentication tokens for terminal login. |
| `/api/auth/google` | Next Auth & Google OAuth 2.0 credential verification with MongoDB Atlas persistence (`Zeus.users`). |
| `/#docs` | Comprehensive documentation on installing the CLI across Linux, macOS, and Windows, core architecture, and commands. |

---

## 4. Whitelist Render URL in Google Cloud & MongoDB Atlas

1. **Google Cloud Console**:
   - Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
   - Under **Authorized JavaScript origins**, add your Render URL: `https://<your-service>.onrender.com`.
   - Under **Authorized redirect URIs**, add `https://<your-service>.onrender.com` and `https://<your-service>.onrender.com/`.
2. **MongoDB Atlas**:
   - In MongoDB Atlas, go to **Network Access** &rarr; **IP Access List**.
   - Add `0.0.0.0/0` (Allow access from anywhere) so Render's cloud servers can connect to your database.
