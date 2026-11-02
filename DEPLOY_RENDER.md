# Deploying Zeus Landing Page to Render

This landing page is production-ready for deployment on **Render** ([https://render.com](https://render.com)).

---

## Option 1: 1-Click Blueprint Deploy (Recommended)

1. Push your repository to **GitHub** or **GitLab**.
2. Log in to your [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** &rarr; **Blueprint**.
4. Select your repository.
5. Render will automatically detect [`render.yaml`](./render.yaml).
6. Click **Apply**.
   - Render automatically provisions the web service, configures environment variables, and enables SSL!

---

## Option 2: Deploy as a Web Service (Manual)

1. In the [Render Dashboard](https://dashboard.render.com/), click **New +** &rarr; **Web Service**.
2. Connect your GitHub repository.
3. Configure the following fields:
   - **Name**: `zeus-landing-page`
   - **Language / Runtime**: `Python 3`
   - **Root Directory**: `marketing_landing` (or leave empty if deploying from repo root)
   - **Build Command**: `pip install -r ../requirements.txt` (or leave empty)
   - **Start Command**: `python server.py`
   - **Plan**: `Free`
4. Add Environment Variables:
   - `PORT`: `10000`
   - `GOOGLE_CLIENT_ID`: `644632951361-d2j5eiu4ur41abjafjrtcpk5oenh4d6r.apps.googleusercontent.com`
   - `GOOGLE_CLIENT_SECRET`: `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`
5. Click **Create Web Service**.

---

## Option 3: Deploy as a Free Static Site (Fastest)

If you only need static hosting without backend server routes:
1. In the Render Dashboard, click **New +** &rarr; **Static Site**.
2. Connect your GitHub repository.
3. Configure:
   - **Name**: `zeus-landing`
   - **Publish Directory**: `marketing_landing`
   - **Build Command**: *(leave blank)*
4. Click **Create Static Site**.
   - Your site will be live instantly with a free `https://zeus-landing.onrender.com` URL.

---

## Configured Features
- **Zero-Blur Footer Art**: The statue illustration in the footer is rendered with full 100% crisp sharpness without CSS Gaussian blur or dimming.
- **Google OAuth 2.0**: Integrated with Client ID `644632951361-d2j5eiu4ur41abjafjrtcpk5oenh4d6r.apps.googleusercontent.com` and Client Secret `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`.
- **GitHub Login**: Built with the matching brutalist monochrome theme.
- **Zeus Branding & Black-and-White Theme**: Retains clean grayscale styling and Zeus agent identity.
- **Fast Local & Cloud Server**: [`server.py`](./server.py) provides zero-dependency high performance static file delivery with health check endpoints.

