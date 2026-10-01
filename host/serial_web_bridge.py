#!/usr/bin/env python3
"""Local web control bridge for the ESP32 BLE mouse prototype."""

from __future__ import annotations

import glob
import json
import os
import select
import termios
import time
import threading
import tty
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
CAPTURE_FILE = WEB_ROOT / "current.jpg"
PORT = 8765
SERIAL_CANDIDATES = ["/dev/cu.usbmodem101", "/dev/cu.usbmodem1101"]


def find_serial_port() -> str | None:
    for port in SERIAL_CANDIDATES:
        if os.path.exists(port):
            return port
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[0] if ports else None


class SerialBridge:
    def __init__(self) -> None:
        self._fd: int | None = None
        self._port: str | None = None
        self._lock = threading.Lock()

    def connect(self) -> str:
        if self._fd is not None:
            return self._port or "unknown"
        port = find_serial_port()
        if not port:
            raise RuntimeError("No ESP32 USB serial port found")
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd
        self._port = port
        return port

    def command(self, command: str) -> str:
        with self._lock:
            port = self.connect()
            assert self._fd is not None
            # A previous command can leave its response in the USB CDC input
            # buffer. If we read that stale line for /status, the UI may show
            # "moved" as if the BLE link were disconnected. Flush only before
            # writing the next command; the response after this write belongs
            # to the command we are about to send.
            termios.tcflush(self._fd, termios.TCIFLUSH)
            os.write(self._fd, (command.strip() + "\n").encode())
            deadline = time.monotonic() + 0.8
            chunks: list[bytes] = []
            while time.monotonic() < deadline:
                readable, _, _ = select.select([self._fd], [], [], 0.05)
                if not readable:
                    continue
                chunks.append(os.read(self._fd, 4096))
                if b"\n" in chunks[-1]:
                    break
            response = b"".join(chunks).decode(errors="replace").strip()
            return response or f"sent via {port}"

    def status(self) -> dict[str, str | bool]:
        try:
            response = self.command("/status")
            return {
                "connected": "BLE connected" in response,
                "port": self._port or "unknown",
                "response": response,
            }
        except Exception as exc:  # Prototype endpoint: return diagnostics to the UI.
            return {"connected": False, "port": self._port or "none", "response": str(exc)}


bridge = SerialBridge()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/status":
            body = json.dumps(bridge.status(), ensure_ascii=False).encode()
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/current.jpg" and CAPTURE_FILE.exists():
            self._send(200, CAPTURE_FILE.read_bytes(), "image/jpeg")
            return
        if path in ("/", "/index.html"):
            body = (WEB_ROOT / "index.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/command":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            command = str(payload.get("command", "")).strip()
            allowed = command.startswith(("/status", "/home", "/move ", "/click left", "/down left", "/up left", "/scroll "))
            if not allowed:
                raise ValueError("Unsupported command")
            response = bridge.command(command)
            self._send(200, json.dumps({"ok": True, "response": response}).encode(), "application/json")
        except Exception as exc:
            self._send(400, json.dumps({"ok": False, "error": str(exc)}).encode(), "application/json")

    def log_message(self, format: str, *args: object) -> None:
        print(format % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"iPad Control Bridge: http://127.0.0.1:{PORT}")
    print("Keep AirPlay mirroring open in a separate Mac window.")
    server.serve_forever()
