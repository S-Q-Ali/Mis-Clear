"""Single-command local dev runner: backend + frontend (+ optional tunnel).

Runs from any shell (PowerShell, Git Bash, cmd) but must operate on the repo
root, because the backend imports the top-level ``tools`` package. Optional
``--tunnel`` exposes the backend through a Cloudflare quick tunnel (the
third-party route the Colab worker polls).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND_APP = "app.backend.main:app"
FRONTEND_PORT = 5173
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def repo_root() -> Path:
    """Return the project root (parent of this script's directory)."""
    return Path(__file__).resolve().parents[1]


def parse_tunnel_url(text: str) -> str | None:
    """Extract the first ``https://<...>.trycloudflare.com`` URL, if present."""
    match = TUNNEL_URL_RE.search(text)
    return match.group(0) if match else None


def is_port_free(host: str, port: int) -> bool:
    """True if a TCP socket can bind ``host:port`` (i.e. nothing is listening)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def build_backend_command(host: str, port: int) -> list[str]:
    return ["uv", "run", "uvicorn", BACKEND_APP, "--host", host, "--port", str(port)]


def build_frontend_command() -> list[str]:
    return ["npm", "run", "dev"]


def build_tunnel_command(host: str, port: int) -> list[str]:
    return ["cloudflared", "tunnel", "--url", f"http://{host}:{port}"]


def backend_env(colab_only: bool) -> dict[str, str]:
    """Env overrides for the backend process (merged over the current env).

    ``colab_only`` clears ``PG_OLLAMA_URL`` so ``default_router`` wires no local
    Ollama backend — heavy AI work goes to the Colab worker only.
    """
    if colab_only:
        return {"PG_OLLAMA_URL": ""}
    return {}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Privacy Guardian locally.")
    parser.add_argument("--host", default=os.environ.get("PG_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PG_PORT", "8000")))
    parser.add_argument("--no-backend", action="store_true", help="skip the backend")
    parser.add_argument("--no-frontend", action="store_true", help="skip the frontend")
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="expose the backend via a Cloudflare quick tunnel (for Colab)",
    )
    parser.add_argument(
        "--colab-only",
        action="store_true",
        help="disable the local Ollama fallback (Colab worker only)",
    )
    return parser.parse_args(argv)


def _popen(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    kwargs: dict = {
        "cwd": str(cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _pump(proc: subprocess.Popen, prefix: str, on_line=None) -> None:
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if not line:
            continue
        print(f"{prefix} {line}", flush=True)
        if on_line is not None:
            on_line(line)


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()


def _resolve(exe: str) -> str | None:
    return shutil.which(exe)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = repo_root()

    if not (root / "app" / "backend" / "main.py").is_file():
        print(f"[dev] ERROR: not a Privacy Guardian checkout: {root}", file=sys.stderr)
        return 1
    if args.no_backend and args.no_frontend:
        print("[dev] ERROR: nothing to run (both --no-backend and --no-frontend).", file=sys.stderr)
        return 1

    os.chdir(root)

    if not args.no_backend and not is_port_free(args.host, args.port):
        print(
            f"[dev] ERROR: {args.host}:{args.port} is already in use "
            "(backend already running?). Stop it first, e.g. Stop-Process, "
            "or pass --port N.",
            file=sys.stderr,
        )
        return 1
    if not args.no_frontend and not is_port_free("127.0.0.1", FRONTEND_PORT):
        print(
            f"[dev] ERROR: 127.0.0.1:{FRONTEND_PORT} is already in use "
            "(frontend already running?). Stop it first.",
            file=sys.stderr,
        )
        return 1

    procs: list[tuple[subprocess.Popen, str]] = []
    pumps: list[tuple[subprocess.Popen, str, object]] = []
    threads: list[threading.Thread] = []

    try:
        if not args.no_backend:
            print(f"[dev] backend  -> http://{args.host}:{args.port}  (docs: /docs)")
            if args.colab_only:
                print("[dev] colab-only: local Ollama fallback disabled")
            backend_process_env = {**os.environ, **backend_env(args.colab_only)}
            backend_proc = _popen(
                build_backend_command(args.host, args.port),
                root,
                env=backend_process_env,
            )
            procs.append((backend_proc, "[backend]"))
            pumps.append((backend_proc, "[backend]", None))

        if not args.no_frontend:
            npm = _resolve("npm")
            if npm is None:
                print("[dev] ERROR: npm not found on PATH.", file=sys.stderr)
                raise SystemExit(1)
            print(f"[dev] frontend -> http://127.0.0.1:{FRONTEND_PORT}")
            frontend_cmd = [npm, *build_frontend_command()[1:]]
            frontend_proc = _popen(frontend_cmd, root / "app" / "frontend")
            procs.append((frontend_proc, "[frontend]"))
            pumps.append((frontend_proc, "[frontend]", None))

        if args.tunnel:
            cloudflared = _resolve("cloudflared")
            if cloudflared is None:
                print("[dev] WARN: cloudflared not found; tunnel skipped.", file=sys.stderr)
            else:
                found = {"url": None}

                def _on_line(line: str) -> None:
                    url = parse_tunnel_url(line)
                    if url and found["url"] is None:
                        found["url"] = url
                        print(f"[dev] TUNNEL URL: {url}")
                        print(f"[dev] set PG_COLAB_JOB_DISPATCHER_URL={url}/api")

                tunnel_cmd = [cloudflared, *build_tunnel_command(args.host, args.port)[1:]]
                tunnel_proc = _popen(tunnel_cmd, root)
                procs.append((tunnel_proc, "[tunnel]"))
                pumps.append((tunnel_proc, "[tunnel]", _on_line))

        for proc, prefix, callback in pumps:
            threads.append(threading.Thread(target=_pump, args=(proc, prefix, callback), daemon=True))
        for thread in threads:
            thread.start()

        print("[dev] running — press Ctrl+C to stop.")
        while any(proc.poll() is None for proc, _ in procs):
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n[dev] stopping...")
    except FileNotFoundError as exc:
        print(f"[dev] ERROR: could not launch {exc}", file=sys.stderr)
        return 1
    finally:
        for proc, _ in procs:
            _terminate(proc)
        for proc, _ in procs:
            with contextlib.suppress(Exception):
                proc.wait(timeout=10)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
