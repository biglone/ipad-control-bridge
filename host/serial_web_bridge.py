#!/usr/bin/env python3
"""Local web control bridge for the ESP32 BLE mouse prototype."""

from __future__ import annotations

import glob
import json
import os
import select
import sys
import termios
import time
import threading
import tty
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional on minimal host installs
    Image = None


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
CAPTURE_FILE = WEB_ROOT / "current.jpg"
PORT = int(os.environ.get("IPAD_BRIDGE_PORT", "8765"))
BIND_HOST = os.environ.get("IPAD_BRIDGE_HOST", "0.0.0.0")
if sys.platform == "darwin":
    SERIAL_CANDIDATES = ["/dev/cu.usbmodem101", "/dev/cu.usbmodem1101"]
    SERIAL_GLOBS = ["/dev/cu.usbmodem*", "/dev/tty.usbmodem*"]
else:
    SERIAL_CANDIDATES = ["/dev/ttyACM0", "/dev/ttyUSB0"]
    SERIAL_GLOBS = ["/dev/ttyACM*", "/dev/ttyUSB*"]


def find_serial_port() -> str | None:
    for port in SERIAL_CANDIDATES:
        if os.path.exists(port):
            return port
    ports = sorted(port for pattern in SERIAL_GLOBS for port in glob.glob(pattern))
    return ports[0] if ports else None


class SerialBridge:
    def __init__(self) -> None:
        self._fd: int | None = None
        self._port: str | None = None
        self._lock = threading.Lock()
        self._cursor: tuple[int, int] | None = None

    def _disconnect(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self._port = None

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
            for attempt in range(2):
                try:
                    port = self.connect()
                    assert self._fd is not None
                    # A previous command can leave its response in the USB CDC
                    # input buffer. Flush it before writing the next command.
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
                    if response and command.startswith("/move "):
                        try:
                            dx, dy = (int(value.strip()) for value in command[6:].split(",", 1))
                            if self._cursor is not None:
                                self._cursor = (self._cursor[0] + dx, self._cursor[1] + dy)
                        except ValueError:
                            pass
                    return response or f"sent via {port}"
                except OSError:
                    self._disconnect()
                    if attempt == 1:
                        raise
            raise RuntimeError("Serial command retry failed")

    def status(self) -> dict[str, str | bool]:
        try:
            response = self.command("/status")
            return {
                "connected": "BLE connected" in response,
                "port": self._port or "unknown",
                "response": response,
                "calibrated": self._cursor is not None,
                "cursor": self._cursor,
            }
        except Exception as exc:  # Prototype endpoint: return diagnostics to the UI.
            return {
                "connected": False,
                "port": self._port or "none",
                "response": str(exc),
                "calibrated": self._cursor is not None,
                "cursor": self._cursor,
            }

    def calibrate(self) -> str:
        response = self.command("/edge")
        if "pointer at top-left edge" not in response:
            raise RuntimeError(response or "ESP32 未确认校准成功")
        self._cursor = (0, 0)
        return response

    def click_at(self, x: int, y: int, width: int, height: int) -> str:
        if self._cursor is None:
            raise RuntimeError("请先校准鼠标位置")
        if width <= 0 or height <= 0:
            raise ValueError("无效的 iPad 画面尺寸")
        target = (max(0, min(width - 1, x)), max(0, min(height - 1, y)))
        dx = target[0] - self._cursor[0]
        dy = target[1] - self._cursor[1]
        if dx or dy:
            self.command(f"/move {dx},{dy}")
        response = self.command("/click left")
        self._cursor = target
        return response


bridge = SerialBridge()


_frame_info_cache: dict[str, object] = {
    "mtime_ns": None,
    "width": 0,
    "height": 0,
    "content_rect": None,
}


def frame_info() -> dict[str, object]:
    """Return the source frame size and the non-black active video rectangle."""
    try:
        stat = CAPTURE_FILE.stat()
    except OSError:
        return {"width": 0, "height": 0, "content_rect": None}
    if _frame_info_cache["mtime_ns"] == stat.st_mtime_ns:
        return {key: _frame_info_cache[key] for key in ("width", "height", "content_rect")}

    width = height = 0
    content_rect: dict[str, int] | None = None
    if Image is not None:
        try:
            with Image.open(CAPTURE_FILE) as image:
                width, height = image.size
                # Downsample for cheap border detection. The capture currently
                # contains a 4:3 iPad image letterboxed inside a 16:9 frame.
                sample_width = min(width, 480)
                sample_height = max(1, round(height * sample_width / width))
                sample = image.convert("L").resize((sample_width, sample_height))
                pixels = sample.load()
                threshold = 8
                active_columns = [
                    x for x in range(sample_width)
                    if sum(pixels[x, y] > threshold for y in range(sample_height)) > sample_height * 0.1
                ]
                active_rows = [
                    y for y in range(sample_height)
                    if sum(pixels[x, y] > threshold for x in range(sample_width)) > sample_width * 0.1
                ]
                if active_columns and active_rows:
                    left = round(min(active_columns) * width / sample_width)
                    right = round((max(active_columns) + 1) * width / sample_width)
                    top = round(min(active_rows) * height / sample_height)
                    bottom = round((max(active_rows) + 1) * height / sample_height)
                    if right - left > width * 0.5 and bottom - top > height * 0.5:
                        content_rect = {"x": left, "y": top, "width": right - left, "height": bottom - top}
        except Exception:
            pass

    _frame_info_cache.update({
        "mtime_ns": stat.st_mtime_ns,
        "width": width,
        "height": height,
        "content_rect": content_rect,
    })
    return {key: _frame_info_cache[key] for key in ("width", "height", "content_rect")}


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
            body = json.dumps({**bridge.status(), "frame": frame_info()}, ensure_ascii=False).encode()
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
        path = urlparse(self.path).path
        if path not in ("/api/command", "/api/mouse"):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if path == "/api/mouse":
                action = str(payload.get("action", "")).strip()
                if action == "calibrate":
                    response = bridge.calibrate()
                elif action == "click_at":
                    response = bridge.click_at(
                        int(payload.get("x", -1)),
                        int(payload.get("y", -1)),
                        int(payload.get("width", 0)),
                        int(payload.get("height", 0)),
                    )
                else:
                    raise ValueError("Unsupported mouse action")
                self._send(200, json.dumps({"ok": True, "response": response}).encode(), "application/json")
                return
            command = str(payload.get("command", "")).strip()
            is_digit_key = len(command) == 6 and command.startswith("/key ") and command[-1] in "0123456789"
            allowed = command.startswith(("/status", "/home", "/move ", "/click left", "/down left", "/up left", "/scroll ")) or is_digit_key
            if not allowed:
                raise ValueError("Unsupported command")
            response = bridge.command(command)
            self._send(200, json.dumps({"ok": True, "response": response}).encode(), "application/json")
        except Exception as exc:
            self._send(400, json.dumps({"ok": False, "error": str(exc)}).encode(), "application/json")

    def log_message(self, format: str, *args: object) -> None:
        print(format % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    display_host = "127.0.0.1" if BIND_HOST == "0.0.0.0" else BIND_HOST
    print(f"iPad Control Bridge: http://{display_host}:{PORT}")
    print("Keep AirPlay mirroring open in a separate Mac window.")
    server.serve_forever()
