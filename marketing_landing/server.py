import http.server
import socketserver
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime

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

MONGODB_URI = os.environ.get(
    "MONGODB_URI",
    "mongodb+srv://charan:Charan1234@<cluster>.mongodb.net/Zeus?retryWrites=true&w=majority"
)

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# MongoDB Database Client Initialization
mongo_client = None
mongo_db = None
mongo_status = "unconnected"

try:
    import pymongo
    import certifi
    if "<cluster>" not in MONGODB_URI:
        mongo_client = pymongo.MongoClient(
            MONGODB_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=3000
        )
        # Verify connection
        mongo_client.admin.command('ping')
        mongo_db = mongo_client["Zeus"]
        mongo_status = "connected"
        print("[MongoDB] Successfully connected to MongoDB Atlas (Zeus database)!")
    else:
        mongo_status = "placeholder_cluster"
        print("[MongoDB] Placeholder <cluster> in MONGODB_URI. Provide actual cluster hostname to connect to MongoDB Atlas.")
except Exception as e:
    mongo_status = f"error: {str(e)}"
    print(f"[MongoDB] Connection notice: {e}")

# In-memory / JSON fallback store for when cluster is not yet configured
fallback_users = {}
fallback_db_path = os.path.join(DIRECTORY, "zeus_users_local.json")
if os.path.exists(fallback_db_path):
    try:
        with open(fallback_db_path, "r", encoding="utf-8") as f:
            fallback_users = json.load(f)
    except:
        fallback_users = {}

def save_user_to_db(user_data):
    """Save or update user in MongoDB or local fallback."""
    user_record = {
        "email": user_data.get("email"),
        "name": user_data.get("name", "Zeus User"),
        "picture": user_data.get("picture"),
        "provider": user_data.get("provider", "google"),
        "provider_id": user_data.get("id"),
        "last_login": datetime.utcnow().isoformat()
    }
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            mongo_db.users.update_one(
                {"email": user_record["email"]},
                {
                    "$set": user_record,
                    "$setOnInsert": {"created_at": datetime.utcnow().isoformat()}
                },
                upsert=True
            )
            print(f"[MongoDB] Saved user {user_record['email']} to Zeus.users collection.")
            return {"saved_to": "mongodb", "status": "success"}
        except Exception as err:
            print(f"[MongoDB] Save failed: {err}. Using local store.")

    # Fallback store
    user_record["created_at"] = fallback_users.get(user_record["email"], {}).get("created_at", datetime.utcnow().isoformat())
    fallback_users[user_record["email"]] = user_record
    try:
        with open(fallback_db_path, "w", encoding="utf-8") as f:
            json.dump(fallback_users, f, indent=2)
    except:
        pass
    return {"saved_to": "local_fallback", "status": "success"}


class ZeusHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def guess_type(self, path):
        if path.endswith(".js"): return "application/javascript; charset=utf-8"
        if path.endswith(".css"): return "text/css; charset=utf-8"
        if path.endswith(".json"): return "application/json; charset=utf-8"
        if path.endswith(".woff2"): return "font/woff2"
        if path.endswith(".webp"): return "image/webp"
        if path.endswith(".svg"): return "image/svg+xml"
        if path.endswith(".jpg") or path.endswith(".jpeg"): return "image/jpeg"
        if path.endswith(".png"): return "image/png"
        if path.endswith(".ico"): return "image/x-icon"
        return super().guess_type(path)

    def end_headers(self):
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
            self.wfile.write(json.dumps({
                "status": "ok",
                "service": "zeus-landing-page",
                "mongodb": mongo_status
            }).encode("utf-8"))
            return

        # Auth & Database status endpoint
        if url.path in ("/api/auth/config", "/api/auth/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "googleClientId": GOOGLE_CLIENT_ID,
                "githubClientId": GITHUB_CLIENT_ID,
                "mongodb": {
                    "status": mongo_status,
                    "database": "Zeus",
                    "collection": "users",
                    "uriConfigured": "<cluster>" not in MONGODB_URI
                }
            }).encode("utf-8"))
            return

        # Fallback root route to index.html
        if url.path == "/" or not os.path.exists(os.path.join(DIRECTORY, url.path.lstrip("/"))):
            if not os.path.splitext(url.path)[1]:
                self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        # Google OAuth verification & MongoDB persistence
        if url.path == "/api/auth/google":
            try:
                data = json.loads(body)
                user_info = data.get("user") or {}
                token = data.get("credential") or data.get("access_token")
                
                # If credential passed from Google Identity Services, decode or verify it
                if token and not user_info.get("email"):
                    verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}" if "credential" in data else "https://www.googleapis.com/oauth2/v3/userinfo"
                    req = urllib.request.Request(
                        verify_url,
                        headers={"Authorization": f"Bearer {token}"} if "access_token" in data else {}
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        user_info = json.loads(resp.read().decode("utf-8"))

                # Persist user into MongoDB Atlas Zeus.users
                user_record = {
                    "id": user_info.get("sub") or user_info.get("id"),
                    "email": user_info.get("email"),
                    "name": user_info.get("name", user_info.get("email", "Google User")),
                    "picture": user_info.get("picture"),
                    "provider": "google"
                }
                db_res = save_user_to_db(user_record)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "user": user_record,
                    "database": db_res
                }).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        # GitHub OAuth / account persistence
        if url.path == "/api/auth/github":
            try:
                data = json.loads(body)
                user_record = {
                    "id": data.get("id") or data.get("username"),
                    "email": data.get("email", f"{data.get('username', 'user')}@github.com"),
                    "name": data.get("name") or data.get("username", "GitHub User"),
                    "picture": data.get("picture") or f"https://github.com/{data.get('username', 'octocat')}.png",
                    "provider": "github"
                }
                db_res = save_user_to_db(user_record)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "user": user_record,
                    "database": db_res
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
