#!/usr/bin/env python3
"""kai diagnostics receiver. Runs on the VPS behind Apache.

kai uploads a JSON report with POST https://ccmai.org/kai-diag/upload; Apache
proxies it to 127.0.0.1:8092. Reports contain logs and system facts only,
never conversations or API keys (see src/kai/diag.py).

kai is open source, so a shared upload token would not be secret. Abuse is
limited instead by size, per-IP rate and total disk caps. Standard library only.

Usage: diag_server.py [--port 8092] [--dir ~/kai-diag]
"""

import argparse
import gzip
import io
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_UPLOAD = 2 * 1024 * 1024  # bytes per report, after decompression
MAX_TOTAL = 500 * 1024 * 1024  # bytes on disk; above this uploads are refused
MIN_INTERVAL = 30  # seconds between uploads from the same IP
MAX_PER_DAY = 20  # uploads per IP per day
REQUIRED_KEYS = {"kai_version", "system", "log"}

args = None
lock = threading.Lock()
uploads_by_ip: dict[str, list[float]] = {}


def dir_size(path: str) -> int:
    return sum(e.stat().st_size for e in os.scandir(path) if e.is_file())


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with lock:
        recent = [t for t in uploads_by_ip.get(ip, []) if now - t < 86400]
        if (recent and now - recent[-1] < MIN_INTERVAL) or len(recent) >= MAX_PER_DAY:
            uploads_by_ip[ip] = recent
            return True
        recent.append(now)
        uploads_by_ip[ip] = recent
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "kai-diag"

    def send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def client_ip(self) -> str:
        # Apache appends the real client IP last; earlier entries can be forged.
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[-1].strip()

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/kai-diag":
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/kai-diag/upload":
            return self.send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return self.send_json(411, {"error": "Content-Length required"})
        if length > MAX_UPLOAD:
            return self.send_json(413, {"error": "report too large"})
        if rate_limited(self.client_ip()):
            return self.send_json(429, {"error": "too many reports, try again later"})
        if dir_size(args.dir) + length > MAX_TOTAL:
            return self.send_json(507, {"error": "receiver full"})

        body = self.rfile.read(length)
        try:
            if self.headers.get("Content-Encoding") == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as f:
                    body = f.read(MAX_UPLOAD + 1)
                if len(body) > MAX_UPLOAD:
                    return self.send_json(413, {"error": "report too large"})
            report = json.loads(body)
        except (OSError, ValueError):
            return self.send_json(400, {"error": "invalid report"})
        if not isinstance(report, dict) or not REQUIRED_KEYS <= report.keys():
            return self.send_json(400, {"error": "invalid report"})

        report_id = secrets.token_hex(4)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}-{report_id}.json"
        tmp = os.path.join(args.dir, f".{name}.part")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"received": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **report}, f, indent=1)
        os.rename(tmp, os.path.join(args.dir, name))
        print(f"received {name} ({len(body)} bytes)", flush=True)
        self.send_json(200, {"id": report_id})

    def log_message(self, fmt, *a) -> None:
        pass  # uploads are logged above; no per-request noise


def main() -> None:
    global args
    p = argparse.ArgumentParser(description="kai diagnostics receiver")
    p.add_argument("--port", type=int, default=8092)
    p.add_argument("--dir", default=os.path.expanduser("~/kai-diag"))
    args = p.parse_args()
    os.makedirs(args.dir, exist_ok=True)
    print(f"kai-diag listening on 127.0.0.1:{args.port}, saving to {args.dir}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
