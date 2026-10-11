import os
import sys
import pkgutil
import importlib.util

# ─────────────────────────────────────────────────────────────────────────────
# 1. Compatibility patch for Python 3.14+ (pkgutil.get_loader was removed)
# ─────────────────────────────────────────────────────────────────────────────
if not hasattr(pkgutil, "get_loader"):
    def _get_loader(name):
        try:
            spec = importlib.util.find_spec(name)
            return spec.loader if spec else None
        except Exception:
            return None
    pkgutil.get_loader = _get_loader

HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <title>RestrictBot Server</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            background: radial-gradient(circle, #0f172a, #020617);
            color: #e2e8f0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            text-align: center;
            padding: 40px;
            border-radius: 16px;
            background: rgba(30, 41, 59, 0.7);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p {
            color: #94a3b8;
            font-size: 1.1rem;
        }
        .status {
            display: inline-block;
            margin-top: 15px;
            padding: 6px 16px;
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
            border-radius: 20px;
            font-weight: 600;
            border: 1px solid rgba(34, 197, 94, 0.4);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎓 Study Bot Server is Active ⚝</h1>
        <p>Powered by 𝗖𝗛𝗢𝗦𝗘𝗡 𝗢𝗡𝗘 ⚝</p>
        <div class="status">● All Systems Operational</div>
    </div>
</body>
</html>
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# 2. Built-in Standard Library Multi-Threaded HTTP Server
# Zero external dependencies, bulletproof on all Python versions (3.10 - 3.14+)
# ─────────────────────────────────────────────────────────────────────────────
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML_CONTENT.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        body = HTML_CONTENT.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

    def log_message(self, format, *args):
        # Concise logging for cloud health checks (Koyeb/Render/Heroku)
        print(f"[HealthCheck] {self.address_string()} - {format % args}")

class ReusableThreadingServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# Also export Flask app for WSGI servers if imported
try:
    from flask import Flask, Response
    app = Flask(__name__)

    @app.route("/", methods=["GET", "HEAD"])
    @app.route("/health", methods=["GET", "HEAD"])
    def welcome():
        return Response(HTML_CONTENT, status=200, mimetype="text/html")
except Exception:
    app = None

def run_server():
    port = int(os.environ.get("PORT", 8000))
    print(f"--- Starting robust Health Check web server on 0.0.0.0:{port} ---")
    server = ReusableThreadingServer(("0.0.0.0", port), HealthCheckHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    run_server()
