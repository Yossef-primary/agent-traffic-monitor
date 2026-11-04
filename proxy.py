#!/usr/bin/env python3
"""proxy.py: the naive agent-traffic proxy for Lab 4.

A reverse proxy that prints every request and response and forwards them
unchanged. Standard library only; nothing to install.

    python3 proxy.py                       # listens on http://localhost:8041
    ANTHROPIC_BASE_URL=http://localhost:8041 claude

Everything Claude Code sends to the API now passes through this program and is
printed to the terminal. The proxy changes nothing: headers go through untouched
(a subscription login needs its bearer token and its `anthropic-beta` header),
and the reply is streamed back byte for byte as it arrives.

    python3 proxy.py --port 9000
    python3 proxy.py --upstream https://chatgpt.com/backend-api/codex   # for Codex

It also appends every request and reply, as they happen, to a JSONL file
(`--log`, default traffic.jsonl) that dashboard.py shows in a browser.
"""

from __future__ import annotations

import argparse
import codecs
import http.client
import itertools
import json
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# Headers that describe one hop of the connection, not the message. They are
# never forwarded. `accept-encoding` is dropped too, so the API answers in plain
# text and what we print is readable.
SKIP = {
    "host", "connection", "keep-alive", "transfer-encoding", "te", "trailers",
    "upgrade", "proxy-authorization", "proxy-authenticate", "accept-encoding",
    "content-length",
}

UPSTREAM = "https://api.anthropic.com"

# The JSONL log: one record per line, written under a lock and flushed at once.
LOG_PATH = "traffic.jsonl"
LOG_LOCK = threading.Lock()
RUN = datetime.now().strftime("%H%M%S")
COUNTER = itertools.count(1)
SECRET = {"authorization", "x-api-key", "cookie"}


def stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def clean_headers(items) -> dict[str, str]:
    """Headers for the log, with secrets cut to 16 chars like the terminal."""
    return {k: (v[:16] + "..." if k.lower() in SECRET else v) for k, v in items}


def log(t: str, rid: str, **fields: object) -> None:
    """Append one record. Never raises: logging must not break the proxy."""
    try:
        line = json.dumps({"t": t, "id": rid, "ts": time.time(), **fields}, ensure_ascii=False)
        with LOG_LOCK, open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception as e:  # noqa: BLE001
        print(f"[{stamp()}] !!! cannot write {LOG_PATH}: {e}", file=sys.stderr, flush=True)


class Tap(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # we print our own lines

    def do_POST(self) -> None:
        self.relay()

    def do_GET(self) -> None:
        self.relay()

    def do_HEAD(self) -> None:
        self.relay()

    def relay(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""

        rid = f"{RUN}-{next(COUNTER)}"
        try:
            parsed, text = json.loads(body), None
        except ValueError:
            parsed, text = None, body.decode("utf-8", "replace") if body else None
        log("req", rid, method=self.command, path=self.path,
            headers=clean_headers(self.headers.items()), body=parsed,
            **({"body_text": text} if text is not None else {}))
        sent = 0
        try:
            sent = self.forward(rid, body)
        except Exception as e:
            log("err", rid, message=f"{type(e).__name__}: {e}")
            raise
        finally:
            log("end", rid, bytes=sent)

    def forward(self, rid: str, body: bytes) -> int:
        """Print, forward, and stream back one request. Returns the bytes sent back."""
        # 1. Print what the agent sent.
        print(f"\n{'=' * 78}\n[{stamp()}] >>> {self.command} {self.path}", flush=True)
        for name, value in self.headers.items():
            if name.lower() in ("authorization", "x-api-key"):
                value = value[:16] + "..."
            print(f"    {name}: {value}")
        if body:
            try:
                print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
            except ValueError:
                print(body.decode("utf-8", "replace"))

        # 2. Forward it, headers intact.
        target = urlsplit(UPSTREAM)
        conn_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        # Connect with a short timeout (a lost SYN must not stall the agent for
        # minutes); the long timeout is for reading a slow stream.
        upstream = conn_cls(target.netloc, timeout=10)
        try:
            upstream.connect()
        except OSError as e:
            print(f"\n[{stamp()}] !!! cannot reach {UPSTREAM}: {e}", flush=True)
            log("resp", rid, status=502, reason="Bad Gateway", headers={})
            log("err", rid, message=f"proxy: cannot reach {UPSTREAM}: {e}")
            self.send_error(502, f"proxy: cannot reach {UPSTREAM}: {e}")
            self.close_connection = True
            return 0
        upstream.sock.settimeout(600)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIP}
        upstream.request(self.command, target.path.rstrip("/") + self.path, body=body or None, headers=headers)
        reply = upstream.getresponse()

        # 3. Stream the reply back as it arrives, printing it on the way.
        print(f"\n[{stamp()}] <<< {reply.status} {reply.reason}", flush=True)
        log("resp", rid, status=reply.status, reason=reply.reason, headers=clean_headers(reply.getheaders()))
        self.send_response(reply.status, reply.reason)
        for name, value in reply.getheaders():
            if name.lower() not in SKIP and name.lower() != "content-encoding":
                self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command == "HEAD":
            self.close_connection = True
            return 0
        # An incremental decoder, so a character split across two chunks is logged whole.
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        sent = 0
        while chunk := reply.read1(4096):  # read1: pass on each chunk as it lands, don't wait for 4096 bytes
            self.wfile.write(chunk)
            self.wfile.flush()
            sent += len(chunk)
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()
            log("chunk", rid, text=decoder.decode(chunk))
        if tail := decoder.decode(b"", final=True):
            log("chunk", rid, text=tail)
        self.close_connection = True
        print(f"\n[{stamp()}] --- done", flush=True)
        return sent


def main() -> None:
    global UPSTREAM, LOG_PATH
    parser = argparse.ArgumentParser(description="Print and forward an agent's API traffic.")
    parser.add_argument("--port", type=int, default=8041)
    parser.add_argument("--upstream", default=UPSTREAM, help="where to forward (default: the Anthropic API)")
    parser.add_argument("--log", default=LOG_PATH, help="JSONL file to append records to (default: traffic.jsonl)")
    args = parser.parse_args()
    UPSTREAM = args.upstream.rstrip("/")
    LOG_PATH = args.log
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Tap)
    print(f"proxy listening on http://localhost:{args.port}  ->  {UPSTREAM}")
    print(f"run the agent with:  ANTHROPIC_BASE_URL=http://localhost:{args.port} claude")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
