# Deploying Zeus Landing Page to Render with MongoDB & OAuth

This landing page is production-ready for deployment on **Render** ([https://render.com](https://render.com)) with integrated **Google OAuth 2.0**, **GitHub Login**, and **MongoDB Atlas** persistence.

---

## 1. Quick Deploy via Render Blueprint (Recommended)

1. Push your repository to **GitHub**.
2. Go to your [Render Dashboard](https://dashboard.render.com/) &rarr; **New +** &rarr; **Blueprint**.
3. Select your repository.
4. Render will automatically detect [`render.yaml`](./render.yaml).
5. In the environment variables prompt, replace `<cluster>` in `MONGODB_URI` with your actual MongoDB Atlas cluster hostname (e.g. `cluster0.abcde.mongodb.net`):
   ```
   MONGODB_URI=mongodb+srv://<db-user>:<db-password>@cluster0.abcde.mongodb.net/Zeus?retryWrites=true&w=majority
   ```
6. Click **Apply**. Render will install dependencies (`pymongo`, `certifi`) and launch the service!

---

## 2. Manual Web Service Deployment

1. In the [Render Dashboard](https://dashboard.render.com/), click **New +** &rarr; **Web Service**.
2. Connect your GitHub repository.
3. Configure the following fields:
   - **Name**: `zeus-landing-page`
   - **Language / Runtime**: `Python 3`
   - **Root Directory**: `marketing_landing` (or leave blank if deploying from repository root)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server.py`
   - **Plan**: `Free`
4. Add the following **Environment Variables**:
   | Key | Value |
   | :--- | :--- |
   | `PORT` | `10000` |
   | `GOOGLE_CLIENT_ID` | `644632951361-d2j5eiu4ur41abjafjrtcpk5oenh4d6r.apps.googleusercontent.com` |
   | `MONGODB_URI` | `mongodb+srv://<db-user>:<db-password>@<your-cluster>.mongodb.net/Zeus?retryWrites=true&w=majority` |
5. Click **Create Web Service**.

---

### "No open ports detected" / "Timed Out" (Docker service)

If the deploy log shows `Zeus Gateway Starting...` and `s6-rc`, Render is building the root
`Dockerfile`, which is the full Zeus agent image (its dashboard listens on localhost only), not
this landing page. Fix the existing service without recreating it:

- **Settings → Build & Deploy → Dockerfile Path:** `./Dockerfile.landing`
- **Docker Build Context Directory:** `.`
- **Health Check Path:** `/health`

Then **Manual Deploy → Deploy latest commit**.

---

## 3. Whitelist Render URL in Google Cloud & MongoDB Atlas

1. **Google Cloud Console**:
   - Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
   - Under **Authorized JavaScript origins**, add your Render URL: `https://your-service.onrender.com`.
   - Under **Authorized redirect URIs**, add `https://your-service.onrender.com` and `https://your-service.onrender.com/`.
2. **MongoDB Atlas**:
   - In MongoDB Atlas, go to **Network Access** &rarr; **IP Access List**.
   - Add `0.0.0.0/0` (Allow access from anywhere) so Render's cloud servers can connect to your database.

---

## Features
- **ZEUS Auth & Access Section**: Replaced "Nous Portal" with an interactive authentication section directly offering Google OAuth 2.0 and GitHub Login.
- **MongoDB Atlas Integration**: Automatically saves and updates users in the `Zeus.users` collection upon login.
- **Zero-Blur Visuals**: Statue illustration in the footer is 100% crisp and sharp.
- **Black-and-White Theme & ZEUS Branding**: Retains high-contrast styling and Zeus agent identity.
