#!/usr/bin/env python3
"""
PRISMA Review Tool — One-command launcher.

Usage:
    python start.py              # Install (first run) + start app
    python start.py --install    # Force reinstall dependencies
    python start.py --port 8000  # Specify backend port (frontend = port + 1000)
    python start.py --no-browser # Don't open browser automatically
    python start.py --cli        # Skip web app, just activate venv for CLI usage
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VENV_DIR = ROOT / ".venv"
WEB_DIR = ROOT / "web"
IS_WIN = platform.system() == "Windows"

# Fix Windows console encoding for Unicode
if IS_WIN:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Helpers ──────────────────────────────────────────────────────────────────

def log(msg: str, style: str = "info") -> None:
    colors = {"info": "\033[96m", "ok": "\033[92m", "warn": "\033[93m", "err": "\033[91m"}
    reset = "\033[0m"
    prefix = {"info": "[i]", "ok": "[+]", "warn": "[!]", "err": "[x]"}.get(style, " . ")
    c = colors.get(style, "")
    print(f"  {c}{prefix}{reset}  {msg}")


def find_free_port(start: int = 8000, end: int = 9000) -> int:
    """Find the first available port in range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def venv_python() -> str:
    if IS_WIN:
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def venv_pip() -> str:
    if IS_WIN:
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    """Run a command, streaming output."""
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=cwd, env=merged_env)
    return result.returncode


# ── Installation ─────────────────────────────────────────────────────────────

def ensure_python_venv() -> bool:
    """Create venv if missing. Returns True if freshly created."""
    if Path(venv_python()).exists():
        return False
    log("Creating Python virtual environment...", "info")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    log("Virtual environment created", "ok")
    return True


def install_python_deps(force: bool = False) -> None:
    """Install Python requirements into the venv."""
    marker = VENV_DIR / ".deps_installed"
    if marker.exists() and not force:
        log("Python dependencies already installed (use --install to force)", "ok")
        return

    log("Installing Python dependencies...", "info")
    reqs = ROOT / "requirements.txt"
    # Also need uvicorn + fastapi for the API server
    ret = run([venv_pip(), "install", "-r", str(reqs), "uvicorn[standard]", "fastapi", "python-multipart", "-q"])
    if ret != 0:
        log("Failed to install Python dependencies", "err")
        sys.exit(1)
    marker.write_text("ok")
    log("Python dependencies installed", "ok")


def ensure_node() -> bool:
    """Check Node.js is available."""
    if shutil.which("node") is None:
        log("Node.js not found. Install from https://nodejs.org (v18+)", "err")
        return False
    return True


def install_node_deps(force: bool = False) -> None:
    """Install Node.js dependencies for the web frontend."""
    node_modules = WEB_DIR / "node_modules"
    if node_modules.exists() and not force:
        log("Node dependencies already installed (use --install to force)", "ok")
        return

    log("Installing Node.js dependencies...", "info")
    npm = "npm.cmd" if IS_WIN else "npm"
    ret = run([npm, "install"], cwd=WEB_DIR)
    if ret != 0:
        log("Failed to install Node dependencies", "err")
        sys.exit(1)
    log("Node dependencies installed", "ok")


def ensure_config() -> None:
    """Copy config.template.yaml to config.yaml if it doesn't exist."""
    config = ROOT / "config.yaml"
    template = ROOT / "config.template.yaml"
    if not config.exists() and template.exists():
        shutil.copy2(template, config)
        log("Created config.yaml from template — edit it with your search queries", "warn")


# ── Running ──────────────────────────────────────────────────────────────────

def start_app(backend_port: int, frontend_port: int, open_browser: bool) -> None:
    """Start FastAPI backend + Next.js frontend, handle cleanup on exit."""
    processes: list[subprocess.Popen] = []

    def cleanup(*_):
        log("Shutting down...", "warn")
        for proc in processes:
            try:
                if IS_WIN:
                    # On Windows, kill process tree
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        log("All processes stopped", "ok")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    if IS_WIN:
        signal.signal(signal.SIGBREAK, cleanup)

    # Start backend (uvicorn)
    log(f"Starting API server on port {backend_port}...", "info")
    backend_cmd = [
        venv_python(), "-m", "uvicorn",
        "api.main:app",
        "--host", "127.0.0.1",
        "--port", str(backend_port),
    ]
    kwargs = {}
    if not IS_WIN:
        kwargs["preexec_fn"] = os.setsid
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    backend_proc = subprocess.Popen(backend_cmd, cwd=ROOT, **kwargs)
    processes.append(backend_proc)

    # Start frontend (next dev)
    log(f"Starting web app on port {frontend_port}...", "info")
    npm = "npm.cmd" if IS_WIN else "npm"
    frontend_env = {
        **os.environ,
        "NEXT_PUBLIC_API_URL": f"http://localhost:{backend_port}",
    }
    frontend_cmd = [npm, "run", "dev", "--", "--port", str(frontend_port)]
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=WEB_DIR, env=frontend_env, **kwargs)
    processes.append(frontend_proc)

    url = f"http://localhost:{frontend_port}"

    # Wait for frontend to be ready, then open browser
    if open_browser:
        log("Waiting for web app to be ready...", "info")
        import urllib.request
        for _ in range(60):  # up to 60 seconds
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except Exception:
                time.sleep(1)
        log(f"Opening {url} in your browser...", "ok")
        webbrowser.open(url)

    print()
    print(f"\033[92m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
    print(f"\033[92m  PRISMA Review Tool is running!\033[0m")
    print()
    print(f"    Web app:     \033[96m{url}\033[0m")
    print(f"    API server:  \033[96mhttp://localhost:{backend_port}\033[0m")
    print(f"    API docs:    \033[96mhttp://localhost:{backend_port}/docs\033[0m")
    print()
    print(f"    Press \033[93mCtrl+C\033[0m to stop")
    print(f"\033[92m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
    print()

    # Wait for either process to exit
    try:
        while True:
            for proc in processes:
                ret = proc.poll()
                if ret is not None:
                    log(f"Process exited with code {ret}", "warn" if ret else "ok")
                    cleanup()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


def cli_mode() -> None:
    """Print activation instructions for CLI usage."""
    print()
    print(f"\033[92m  PRISMA Review Tool — CLI Mode\033[0m")
    print()
    if IS_WIN:
        activate = f"{VENV_DIR}\\Scripts\\activate"
        print(f"    Activate venv:  \033[96m{activate}\033[0m")
    else:
        activate = f"source {VENV_DIR}/bin/activate"
        print(f"    Activate venv:  \033[96m{activate}\033[0m")
    print()
    print(f"    Then run:")
    print(f"      \033[96mpython -m prisma_review status\033[0m      # Check pipeline state")
    print(f"      \033[96mpython -m prisma_review run-all\033[0m     # Full pipeline")
    print(f"      \033[96mpython -m prisma_review search\033[0m      # Search databases")
    print(f"      \033[96mpython -m prisma_review dedup\033[0m       # Deduplicate")
    print(f"      \033[96mpython -m prisma_review screen-rules\033[0m # Keyword screening")
    print(f"      \033[96mpython -m prisma_review export\033[0m      # Export .bib + .csv")
    print()
    print(f"    See \033[96mpython -m prisma_review --help\033[0m for all commands")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PRISMA Review Tool — install & launch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start.py              Start the web app (installs deps on first run)
  python start.py --install    Force reinstall all dependencies
  python start.py --port 9000  Use custom port (frontend at 10000)
  python start.py --cli        Just set up venv for CLI usage
        """,
    )
    parser.add_argument("--install", action="store_true", help="Force reinstall all dependencies")
    parser.add_argument("--port", type=int, default=0, help="Backend port (0 = auto-detect, default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--cli", action="store_true", help="CLI mode — just set up venv, don't start web app")
    args = parser.parse_args()

    print()
    print(f"\033[96m  ╔═══════════════════════════════════════════════╗\033[0m")
    print(f"\033[96m  ║    PRISMA Review Tool                        ║\033[0m")
    print(f"\033[96m  ║    Systematic Literature Review (PRISMA 2020) ║\033[0m")
    print(f"\033[96m  ╚═══════════════════════════════════════════════╝\033[0m")
    print()

    # 1. Python venv + deps
    fresh = ensure_python_venv()
    install_python_deps(force=args.install or fresh)

    # 2. Config
    ensure_config()

    # CLI-only mode
    if args.cli:
        cli_mode()
        return

    # 3. Node deps
    if not ensure_node():
        sys.exit(1)
    install_node_deps(force=args.install)

    # 4. Find ports
    if args.port:
        backend_port = args.port
    else:
        backend_port = find_free_port(8000, 9000)
    frontend_port = find_free_port(backend_port + 1000, backend_port + 2000)

    # 5. Launch
    start_app(backend_port, frontend_port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
