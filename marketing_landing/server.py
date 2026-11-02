import http.server
import socketserver
import os
import sys
import json
import urllib.request
import urllib.parse

PORT = int(os.environ.get("PORT", 8080))
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "644632951361-d2j5eiu4ur41abjafjrtcpk5oenh4d6r.apps.googleusercontent.com"
)
GOOGLE_CLIENT_SECRET = os.environ.get(
    "GOOGLE_CLIENT_SECRET",
    "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"
)
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class ZeusHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def guess_type(self, path):
        # Ensure proper MIME types for modern web assets
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        if path.endswith(".json"):
            return "application/json; charset=utf-8"
        if path.endswith(".woff2"):
            return "font/woff2"
        if path.endswith(".webp"):
            return "image/webp"
        if path.endswith(".svg"):
            return "image/svg+xml"
        if path.endswith(".jpg") or path.endswith(".jpeg"):
            return "image/jpeg"
        if path.endswith(".png"):
            return "image/png"
        return super().guess_type(path)

    def end_headers(self):
        # Permissive security headers for Render deployment and Google OAuth
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)

        # Health check for Render
        if url.path in ("/health", "/api/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "zeus-landing-page"}).encode("utf-8"))
            return

        # Auth configuration endpoint for frontend
        if url.path == "/api/auth/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "googleClientId": GOOGLE_CLIENT_ID,
                "githubClientId": GITHUB_CLIENT_ID
            }).encode("utf-8"))
            return

        # Fallback root route to index.html
        if url.path == "/" or not os.path.exists(os.path.join(DIRECTORY, url.path.lstrip("/"))):
            if not os.path.splitext(url.path)[1]:
                self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)

        # Google OAuth verification / token exchange
        if url.path == "/api/auth/google":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                token = data.get("credential") or data.get("access_token")
                
                # Verify token with Google's tokeninfo endpoint
                verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}" if "credential" in data else "https://www.googleapis.com/oauth2/v3/userinfo"
                req = urllib.request.Request(
                    verify_url,
                    headers={"Authorization": f"Bearer {token}"} if "access_token" in data else {}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    user_info = json.loads(resp.read().decode("utf-8"))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "user": {
                        "id": user_info.get("sub"),
                        "email": user_info.get("email"),
                        "name": user_info.get("name", user_info.get("email", "User")),
                        "picture": user_info.get("picture"),
                        "provider": "google"
                    }
                }).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

if __name__ == "__main__":
    print(f"Starting Zeus Landing Page server on port {PORT}...")
    with socketserver.TCPServer(("0.0.0.0", PORT), ZeusHandler) as httpd:
        print(f"Server serving at http://0.0.0.0:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server stopped.")

