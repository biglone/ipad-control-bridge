#!/bin/sh
set -eu

# One-command local service manager for the Mac prototype.
# Usage: ./service.sh start|stop|restart|status|logs

HOST_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
RUN_DIR="$HOST_DIR/.run"
LOG_DIR="$HOST_DIR/logs"
CAPTURE_PID="$RUN_DIR/capture.pid"
WEB_PID="$RUN_DIR/web.pid"
CAPTURE_LOG="$LOG_DIR/capture.log"
WEB_LOG="$LOG_DIR/web.log"
PORT="${IPAD_BRIDGE_PORT:-8765}"
HEALTH_URL="http://127.0.0.1:${PORT}"

get_lan_host() {
  case "$(uname -s)" in
    Darwin)
      interface=$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')
      if [ -n "${interface:-}" ]; then
        ipconfig getifaddr "$interface" 2>/dev/null && return 0
      fi
      ;;
    Linux)
      hostname -I 2>/dev/null | awk '{print $1; exit}' && return 0
      ;;
  esac
  echo "127.0.0.1"
}

WEB_HOST_DISPLAY="$(get_lan_host)"
WEB_URL="http://${WEB_HOST_DISPLAY}:${PORT}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

is_running() {
  pid_file="$1"
  [ -s "$pid_file" ] || return 1
  pid=$(cat "$pid_file")
  kill -0 "$pid" 2>/dev/null || return 1
  return 0
}

stop_pid() {
  pid_file="$1"
  [ -s "$pid_file" ] || return 0
  pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    i=0
    while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 20 ]; do
      sleep 0.1
      i=$((i + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pid_file"
}

start_capture() {
  if is_running "$CAPTURE_PID"; then
    echo "HDMI 采集已运行（PID $(cat "$CAPTURE_PID")）"
    return 0
  fi
  rm -f "$CAPTURE_PID"
  echo "正在启动 HDMI 采集…"
  nohup "$HOST_DIR/capture_card_ffmpeg.sh" auto >>"$CAPTURE_LOG" 2>&1 &
  echo $! >"$CAPTURE_PID"
  sleep 2
  if ! is_running "$CAPTURE_PID"; then
    echo "HDMI 采集启动失败，请查看：$CAPTURE_LOG" >&2
    return 1
  fi
  echo "HDMI 采集已启动（PID $(cat "$CAPTURE_PID")）"
}

start_web() {
  if is_running "$WEB_PID"; then
    echo "网页服务已运行（PID $(cat "$WEB_PID")）"
    return 0
  fi
  rm -f "$WEB_PID"
  echo "正在启动网页控制服务…"
  nohup python3 "$HOST_DIR/serial_web_bridge.py" >>"$WEB_LOG" 2>&1 &
  echo $! >"$WEB_PID"
  sleep 1
  if ! is_running "$WEB_PID"; then
    echo "网页服务启动失败，请查看：$WEB_LOG" >&2
    return 1
  fi
  echo "网页服务已启动：$WEB_URL"
}

status() {
  if is_running "$CAPTURE_PID"; then
    echo "HDMI 采集：运行中（PID $(cat "$CAPTURE_PID")）"
  else
    echo "HDMI 采集：未运行"
  fi
  if is_running "$WEB_PID"; then
    echo "网页服务：运行中（PID $(cat "$WEB_PID")）"
    if command -v curl >/dev/null 2>&1; then
      printf "ESP32 状态："
      curl -fsS "$HEALTH_URL/api/status" 2>/dev/null || echo "无法读取"
    fi
  else
    echo "网页服务：未运行"
  fi
}

case "${1:-status}" in
  start)
    start_capture
    start_web
    echo "打开：$WEB_URL"
    ;;
  stop)
    stop_pid "$WEB_PID"
    stop_pid "$CAPTURE_PID"
    echo "服务已停止"
    ;;
  restart)
    stop_pid "$WEB_PID"
    stop_pid "$CAPTURE_PID"
    sleep 1
    start_capture
    start_web
    echo "服务已重启，打开：$WEB_URL"
    ;;
  status)
    status
    ;;
  logs)
    echo "采集日志：$CAPTURE_LOG"
    echo "网页日志：$WEB_LOG"
    ;;
  *)
    echo "用法：$0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
