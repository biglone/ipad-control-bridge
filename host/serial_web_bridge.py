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
from datetime import datetime, timezone
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
CALIBRATION_FILE = ROOT / ".run" / "mouse-calibration.json"
CALIBRATION_LOG = ROOT / ".run" / "mouse-calibration.log"
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
        self._calibration_points: list[dict[str, int]] = []
        self._model: list[float] | None = None
        self._locked_frame: dict[str, int] | None = None
        self._load_calibration()

    def _log(self, event: str, **details: object) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "cursor": self._cursor,
            "points": len(self._calibration_points),
            **details,
        }
        try:
            CALIBRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CALIBRATION_LOG.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_calibration(self) -> None:
        try:
            data = json.loads(CALIBRATION_FILE.read_text())
            self._calibration_points = list(data.get("points", []))
            cursor = data.get("cursor")
            if cursor is None and self._calibration_points:
                last_point = self._calibration_points[-1]
                cursor = (last_point.get("command_x"), last_point.get("command_y"))
            self._cursor = tuple(int(value) for value in cursor) if cursor and len(cursor) == 2 else None
            model = data.get("model")
            self._model = [float(value) for value in model] if model and len(model) == 6 else None
            locked_frame = data.get("locked_frame")
            self._locked_frame = locked_frame if isinstance(locked_frame, dict) else None
        except (OSError, ValueError, TypeError):
            self._calibration_points = []
            self._cursor = None
            self._model = None
            self._locked_frame = None

    def _save_calibration(self) -> None:
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps({
            "points": self._calibration_points,
            "cursor": self._cursor,
            "model": self._model,
            "locked_frame": self._locked_frame,
        }))

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
                                self._save_calibration()
                        except ValueError:
                            pass
                    self._log("command", command=command, response=response)
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
                "calibration_ready": self._model is not None,
                "calibration_points": len(self._calibration_points),
            }
        except Exception as exc:  # Prototype endpoint: return diagnostics to the UI.
            return {
                "connected": False,
                "port": self._port or "none",
                "response": str(exc),
                "calibrated": self._cursor is not None,
                "cursor": self._cursor,
                "calibration_ready": self._model is not None,
                "calibration_points": len(self._calibration_points),
            }

    def calibrate(self) -> str:
        response = self.command("/edge")
        if "pointer at top-left edge" not in response:
            raise RuntimeError(response or "ESP32 未确认校准成功")
        self._cursor = (0, 0)
        self._calibration_points = []
        self._model = None
        current_frame = frame_info().get("content_rect")
        self._locked_frame = dict(current_frame) if isinstance(current_frame, dict) else None
        self._save_calibration()
        self._log("calibration_start", response=response, locked_frame=self._locked_frame)
        return response

    def record_calibration_point(self, x: int, y: int) -> str:
        if self._cursor is None:
            raise RuntimeError("请先开始校准")
        point = {"command_x": self._cursor[0], "command_y": self._cursor[1], "screen_x": x, "screen_y": y}
        self._calibration_points = [
            existing for existing in self._calibration_points
            if existing["screen_x"] != x or existing["screen_y"] != y
        ]
        self._calibration_points.append(point)
        self._model = None
        self._save_calibration()
        self._log("record_point", point=point, locked_frame=self._locked_frame)
        return f"已记录校准点 {len(self._calibration_points)}（命令坐标 {self._cursor}，目标坐标 {x},{y}）"

    @staticmethod
    def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> list[float]:
        rows = [matrix[index][:] + [vector[index]] for index in range(3)]
        for column in range(3):
            pivot = max(range(column, 3), key=lambda row: abs(rows[row][column]))
            if abs(rows[pivot][column]) < 1e-9:
                raise ValueError("校准点不能共线")
            rows[column], rows[pivot] = rows[pivot], rows[column]
            divisor = rows[column][column]
            rows[column] = [value / divisor for value in rows[column]]
            for row in range(3):
                if row == column:
                    continue
                factor = rows[row][column]
                rows[row] = [rows[row][i] - factor * rows[column][i] for i in range(4)]
        return [rows[index][3] for index in range(3)]

    def solve_calibration(self) -> str:
        if len(self._calibration_points) < 3:
            raise ValueError("至少需要记录 3 个不共线的校准点")
        rows = [[1.0, point["command_x"], point["command_y"]] for point in self._calibration_points]
        normal = [[sum(row[i] * row[j] for row in rows) for j in range(3)] for i in range(3)]
        x_values = [point["screen_x"] for point in self._calibration_points]
        y_values = [point["screen_y"] for point in self._calibration_points]
        x_model = self._solve_3x3(normal, [sum(rows[index][i] * x_values[index] for index in range(len(rows))) for i in range(3)])
        y_model = self._solve_3x3(normal, [sum(rows[index][i] * y_values[index] for index in range(len(rows))) for i in range(3)])
        self._model = [*x_model, *y_model]
        residuals = []
        for point in self._calibration_points:
            predicted_x = x_model[0] + x_model[1] * point["command_x"] + x_model[2] * point["command_y"]
            predicted_y = y_model[0] + y_model[1] * point["command_x"] + y_model[2] * point["command_y"]
            residuals.append({
                "screen": {"x": point["screen_x"], "y": point["screen_y"]},
                "predicted": {"x": round(predicted_x, 2), "y": round(predicted_y, 2)},
                "error": round(((predicted_x - point["screen_x"]) ** 2 + (predicted_y - point["screen_y"]) ** 2) ** 0.5, 2),
            })
        self._save_calibration()
        max_error = max((item["error"] for item in residuals), default=0)
        self._log("solve_calibration", model=self._model, residuals=residuals,
                  max_error=max_error, locked_frame=self._locked_frame)
        return f"多点校准完成（最大拟合误差 {max_error}px）"

    def click_at(self, x: int, y: int, width: int, height: int) -> str:
        if self._cursor is None:
            raise RuntimeError("请先校准鼠标位置")
        if self._model is None:
            raise RuntimeError("请先完成至少 3 个校准点")
        if width <= 0 or height <= 0:
            raise ValueError("无效的 iPad 画面尺寸")
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        x_offset, x_command, x_cross, y_offset, y_command, y_cross = self._model
        determinant = x_command * y_cross - x_cross * y_command
        if abs(determinant) < 1e-9:
            raise RuntimeError("校准矩阵无效，请重新校准")
        target = (
            round(((x - x_offset) * y_cross - x_cross * (y - y_offset)) / determinant),
            round((x_command * (y - y_offset) - (x - x_offset) * y_command) / determinant),
        )
        dx = target[0] - self._cursor[0]
        dy = target[1] - self._cursor[1]
        if dx or dy:
            self.command(f"/move {dx},{dy}")
        response = self.command("/click left")
        self._cursor = target
        self._save_calibration()
        self._log("click_at", screen_target={"x": x, "y": y}, command_target=target,
                  delta={"x": dx, "y": dy}, response=response, model=self._model,
                  locked_frame=self._locked_frame)
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


def display_frame_info() -> dict[str, object]:
    """Return a stable frame rectangle while calibration/click mapping is active."""
    info = frame_info()
    if bridge._locked_frame is None:
        return info
    return {**info, "content_rect": dict(bridge._locked_frame), "locked": True}


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
            body = json.dumps({**bridge.status(), "frame": display_frame_info()}, ensure_ascii=False).encode()
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/calibration-log":
            try:
                lines = CALIBRATION_LOG.read_text(encoding="utf-8").splitlines()[-100:]
            except OSError:
                lines = []
            body = json.dumps({"entries": [json.loads(line) for line in lines]}, ensure_ascii=False).encode()
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
                if action in ("calibrate", "calibration_start"):
                    response = bridge.calibrate()
                elif action == "record_point":
                    response = bridge.record_calibration_point(int(payload.get("x", -1)), int(payload.get("y", -1)))
                elif action == "solve_calibration":
                    response = bridge.solve_calibration()
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
