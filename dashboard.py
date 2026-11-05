#!/usr/bin/env python3
"""dashboard.py: serve dashboard.html and stream the proxy's JSONL log to it.

    python3 dashboard.py [--port 8050] [--log traffic.jsonl]   # open http://localhost:8050

Standard library only. The server does not parse traffic: it sends each JSONL
line unchanged as one Server-Sent Event (id = line number). All parsing happens
in the page, so live data and reloaded history go through the same code.
"""

from __future__ import annotations

import argparse
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = "traffic.jsonl"
POLL = 0.2
PING_EVERY = 15.0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.serve_page()
        elif path == "/events":
            try:
                self.serve_events()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError):
                pass  # browser went away
        else:
            self.send_error(404)

    def serve_page(self) -> None:
        try:
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                data = f.read()
        except OSError as e:
            self.send_error(500, f"cannot read dashboard.html: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_event(self, data: bytes, event_id: int | None = None, event: str | None = None) -> None:
        parts = []
        if event:
            parts.append(b"event: " + event.encode() + b"\n")
        if event_id is not None:
            parts.append(b"id: " + str(event_id).encode() + b"\n")
        parts.append(b"data: " + data + b"\n\n")
        self.wfile.write(b"".join(parts))

    def serve_events(self) -> None:
        try:
            resume = int(self.headers.get("Last-Event-ID") or 0)
        except ValueError:
            resume = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(b"retry: 1000\n\n")
        self.wfile.flush()

        if resume:
            # The browser remembers more lines than the file has (it was replaced
            # while we were down): tell the page to clear and send everything.
            try:
                with open(LOG_PATH, "rb") as f:
                    have = sum(1 for _ in f)
            except OSError:
                have = 0
            if resume > have:
                resume = 0
                self.send_event(b"{}", event="reset")
                self.wfile.flush()

        line_no = 0      # lines already handled (sent or skipped)
        offset = 0       # byte offset of the first unread byte
        partial = b""    # held-back partial last line
        last_ping = time.monotonic()
        while True:
            try:
                size = os.path.getsize(LOG_PATH)
            except OSError:
                size = 0
            if size < offset:
                # Deleted or truncated: start again from line 1.
                offset, line_no, partial, resume = 0, 0, b"", 0
                self.send_event(b"{}", event="reset")
                self.wfile.flush()
            if size > offset:
                with open(LOG_PATH, "rb") as f:
                    f.seek(offset)
                    data = f.read(size - offset)
                offset += len(data)
                buf = partial + data
                lines = buf.split(b"\n")
                partial = lines.pop()  # incomplete tail (b"" if buf ended with \n)
                for raw in lines:
                    line_no += 1
                    raw = raw.rstrip(b"\r")
                    if line_no <= resume or not raw.strip():
                        continue
                    self.send_event(raw, event_id=line_no)
                self.wfile.flush()
            now = time.monotonic()
            if now - last_ping >= PING_EVERY:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                last_ping = now
            time.sleep(POLL)


def main() -> None:
    global LOG_PATH
    parser = argparse.ArgumentParser(description="Live dashboard for proxy.py traffic.")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--log", default=LOG_PATH, help="JSONL file written by proxy.py --log")
    args = parser.parse_args()
    LOG_PATH = args.log
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"dashboard on http://localhost:{args.port}  (log: {LOG_PATH})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
