"""One-click launcher for the Agent system.

Usage:
    python start_agent.py          # start backend only (port 8000)
    python start_agent.py --dev    # start backend + frontend dev server
"""
import subprocess
import sys
import os
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    dev_mode = "--dev" in sys.argv

    print("=" * 60)
    print("  JobNavigator-IT Agent System")
    print("=" * 60)

    # Start backend
    print("\n[1/2] Starting backend (FastAPI) on http://127.0.0.1:8000 ...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=ROOT,
    )

    if dev_mode:
        print("[2/2] Starting frontend dev server on http://localhost:5173 ...")
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=os.path.join(ROOT, "frontend"),
            shell=True,
        )
        time.sleep(2)
        print("\n" + "=" * 60)
        print("  Frontend:  http://localhost:5173")
        print("  Backend:   http://127.0.0.1:8000")
        print("  API docs:  http://127.0.0.1:8000/docs")
        print("=" * 60)
    else:
        frontend = None
        time.sleep(2)
        print("\n" + "=" * 60)
        print("  Backend:   http://127.0.0.1:8000")
        print("  API docs:  http://127.0.0.1:8000/docs")
        print("  Frontend:  run `cd frontend && npm run dev` separately")
        print("=" * 60)

    print("\nPress Ctrl+C to stop.\n")

    try:
        backend.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        backend.terminate()
        if frontend:
            frontend.terminate()


if __name__ == "__main__":
    main()
