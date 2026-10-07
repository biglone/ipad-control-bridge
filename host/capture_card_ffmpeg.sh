#!/bin/sh
set -eu

# Capture a UVC/HDMI card and keep the web preview image updated.
# macOS uses AVFoundation; Linux uses V4L2.
VIDEO_DEVICE="${1:-auto}"
OUTPUT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/web/current.jpg"
PLATFORM="$(uname -s)"

mkdir -p "$(dirname -- "$OUTPUT")"

if [ "$PLATFORM" = "Darwin" ]; then
  if [ "$VIDEO_DEVICE" = "auto" ]; then
    DEVICE_LIST="$(ffmpeg -f avfoundation -list_devices true -i '' 2>&1 || true)"
    VIDEO_DEVICE="$(printf '%s\n' "$DEVICE_LIST" | awk '/UGREEN 25854/ {for (i = 1; i <= NF; i++) if ($i ~ /^\[[0-9]+\]$/) {gsub(/\[/, "", $i); gsub(/\]/, "", $i); print $i; exit}}')"
  fi
  if [ -z "$VIDEO_DEVICE" ]; then
    echo "找不到 UGREEN 25854 采集卡。"
    echo "请先运行：ffmpeg -f avfoundation -list_devices true -i ''"
    exit 2
  fi
  DEVICE_LIST="$(ffmpeg -f avfoundation -list_devices true -i '' 2>&1 || true)"
  DEVICE_NAME="$(printf '%s\n' "$DEVICE_LIST" | awk -v wanted="[$VIDEO_DEVICE]" '{for (i = 1; i <= NF; i++) if ($i == wanted) {for (j = i + 1; j <= NF; j++) printf "%s%s", (j == i + 1 ? "" : " "), $j; print ""; exit}}')"
  case "$DEVICE_NAME" in
    *UGREEN*25854*) ;;
    *) echo "安全检查失败：设备编号 $VIDEO_DEVICE 当前不是 UGREEN 25854，而是：${DEVICE_NAME:-未知设备}"; exit 3 ;;
  esac
  echo "开始采集 UGREEN 25854，AVFoundation 设备编号 [$VIDEO_DEVICE]"
  echo "输出：$OUTPUT"
  exec ffmpeg \
    -hide_banner -y \
    -f avfoundation -framerate 30 -pixel_format uyvy422 \
    -video_size 1920x1080 -i "${VIDEO_DEVICE}:none" \
    -vf "fps=12" -q:v 3 -f image2 -update 1 "$OUTPUT"
fi

if [ "$PLATFORM" = "Linux" ]; then
  if [ "$VIDEO_DEVICE" = "auto" ]; then
    VIDEO_DEVICE="$(find /dev -maxdepth 1 -type c -name 'video[0-9]*' | sort | head -n 1)"
  fi
  if [ -z "$VIDEO_DEVICE" ] || [ ! -e "$VIDEO_DEVICE" ]; then
    echo "找不到 V4L2 采集设备，请确认 HDMI 采集卡已连接。"
    echo "可用设备：$(find /dev -maxdepth 1 -type c -name 'video[0-9]*' | sort | tr '\n' ' ')"
    exit 2
  fi
  echo "开始采集 Linux V4L2 设备 [$VIDEO_DEVICE]"
  echo "输出：$OUTPUT"
  exec ffmpeg \
    -hide_banner -y \
    -f v4l2 -framerate 30 -input_format uyvy422 \
    -video_size 1920x1080 -i "$VIDEO_DEVICE" \
    -vf "fps=12" -q:v 3 -f image2 -update 1 "$OUTPUT"
fi

echo "不支持的平台：$PLATFORM" >&2
exit 4
