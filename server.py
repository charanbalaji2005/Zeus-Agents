import os
import sys

# Ensure marketing_landing is the working directory
base_dir = os.path.dirname(os.path.abspath(__file__))
marketing_dir = os.path.join(base_dir, "marketing_landing")
os.chdir(marketing_dir)
sys.path.insert(0, marketing_dir)

from server import PORT, socketserver, ZeusHandler

if __name__ == "__main__":
    print(f"Starting Zeus Landing Page server from root on port {PORT}...")
    with socketserver.TCPServer(("0.0.0.0", PORT), ZeusHandler) as httpd:
        print(f"Server serving at http://0.0.0.0:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server stopped.")

