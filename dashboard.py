#!/usr/bin/env python3
"""dashboard.py: serve the live traffic dashboard for proxy.py.

    python3 dashboard.py                              # http://localhost:8050
    python3 dashboard.py --port 8050 --log traffic.jsonl

GET /         the page (dashboard.html, next to this file)
GET /events   Server-Sent Events: every line already in the log, then each new
              line as the proxy writes it. Lines are sent unchanged; the page
              does all the parsing. Standard library only.
"""

from __future__ import annotations

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = Path("traffic.jsonl")
POLL = 0.2          # seconds between checks of the log
PING = 15.0         # seconds of silence before a keep-alive comment
READ = 4 << 20      # read the log in pieces of this many bytes
RESET = b"event: reset\ndata: {}\n\n"


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(piece.count(b"\n") for piece in iter(lambda: f.read(READ), b""))
    except OSError:
        return 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.page()
        elif path == "/events":
            self.events()
        else:
            self.send_error(404)

    def page(self) -> None:
        try:
            data = (HERE / "dashboard.html").read_bytes()
        except OSError as e:
            self.send_error(500, f"cannot read dashboard.html: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def events(self) -> None:
        try:
            resume = int(self.headers.get("Last-Event-ID") or 0)
        except ValueError:
            resume = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.stream(resume)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the browser went away

    def stream(self, resume: int) -> None:
        """Send log lines after line `resume`, then follow the file forever."""
        self.wfile.write(b"retry: 1000\n\n")
        # A resume point past the end means the file was replaced while we were away.
        if resume and count_lines(LOG) < resume:
            self.wfile.write(RESET)
            resume = 0
        offset = line_no = 0
        inode = None
        partial = b""
        last_sent = time.monotonic()
        while True:
            try:
                st = LOG.stat()
                size, ino = st.st_size, st.st_ino
            except OSError:
                size, ino = 0, None
            if size < offset or (inode is not None and ino != inode):
                # Truncated, deleted or replaced: tell the page and start from line 1.
                offset = line_no = resume = 0
                partial = b""
                self.wfile.write(RESET)
            inode = ino
            sent = False
            if size > offset:
                with LOG.open("rb") as f:
                    f.seek(offset)
                    while offset < size:
                        data = f.read(min(READ, size - offset))
                        if not data:
                            break
                        offset += len(data)
                        *lines, partial = (partial + data).split(b"\n")  # hold back a half-written line
                        out = []
                        for line in lines:
                            line_no += 1
                            line = line.rstrip(b"\r")
                            if line_no > resume and line.strip():
                                out.append(b"id: %d\ndata: %s\n\n" % (line_no, line))
                        if out:
                            self.wfile.write(b"".join(out))
                            sent = True
            now = time.monotonic()
            if sent:
                last_sent = now
            elif now - last_sent >= PING:
                self.wfile.write(b": ping\n\n")
                last_sent = now
            time.sleep(POLL)


def main() -> None:
    global LOG
    parser = argparse.ArgumentParser(description="Serve a live dashboard of proxy.py's traffic log.")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--log", default=str(LOG), help="JSONL file written by proxy.py (default: traffic.jsonl)")
    args = parser.parse_args()
    LOG = Path(args.log)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"dashboard on http://localhost:{args.port}  <-  {LOG}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
