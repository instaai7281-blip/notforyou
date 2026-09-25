import os
import subprocess
import time

# Get port from environment or default to 8000 / 8080 / 5000
port = os.environ.get("PORT", "8080")

def main():
    print(f"--- Starting Flask web server on port {port} ---")
    flask_process = None
    try:
        flask_process = subprocess.Popen(["python3", "app.py"])
        print(f"Flask process started with PID: {flask_process.pid}")
    except Exception as e:
        print(f"Failed to start Flask: {e}")

    # Give the web server a few seconds to initialize
    time.sleep(3)

    print("--- Starting Telegram Bot module (devgagan) ---")
    try:
        while True:
            try:
                ret = os.system("python3 -m devgagan")
                print(f"[Main] devgagan exited with code {ret}. Restarting in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received. Shutting down...")
                break
            except Exception as e:
                print(f"Bot encountered an error: {e}. Retrying in 5 seconds...")
                time.sleep(5)
    finally:
        if flask_process:
            print("Terminating Flask process...")
            flask_process.terminate()
            try:
                flask_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                flask_process.kill()
            print("Flask process shut down.")

if __name__ == "__main__":
    main()
