import os
import sys
import subprocess
import time
import pkgutil
import importlib.util

# ─────────────────────────────────────────────────────────────────────────────
# Compatibility patch for Python 3.14+ (pkgutil.get_loader was removed)
# ─────────────────────────────────────────────────────────────────────────────
if not hasattr(pkgutil, "get_loader"):
    def _get_loader(name):
        try:
            spec = importlib.util.find_spec(name)
            return spec.loader if spec else None
        except Exception:
            return None
    pkgutil.get_loader = _get_loader

# Get port from environment or default to 8000 / 8080
port = os.environ.get("PORT", "8000")

def main():
    print(f"--- Starting Health Check web server on port {port} ---")
    web_process = None
    try:
        web_process = subprocess.Popen([sys.executable, "app.py"])
        print(f"Web server process started with PID: {web_process.pid}")
    except Exception as e:
        print(f"Failed to start web server: {e}")

    # Give the web server a moment to bind the port
    time.sleep(2)

    print("--- Starting Telegram Bot module (toxic) ---")
    try:
        while True:
            try:
                ret = os.system(f"{sys.executable} -m toxic")
                print(f"[Main] toxic exited with code {ret}. Restarting in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received. Shutting down...")
                break
            except Exception as e:
                print(f"Bot encountered an error: {e}. Retrying in 5 seconds...")
                time.sleep(5)
    finally:
        if web_process:
            print("Terminating web server process...")
            web_process.terminate()
            try:
                web_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                web_process.kill()
            print("Web server process shut down.")

if __name__ == "__main__":
    main()
