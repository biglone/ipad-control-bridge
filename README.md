# iPad Control Bridge

一个面向 Mac + iPad Air 4 + ESP32-S3 的本地控制原型。

当前阶段已经完成：ESP32-S3 被 iPad 识别为 BLE 鼠标，并可通过 Mac 的 USB 串口发送移动和点击命令。

项目目标：在不使用 AnyDesk、向日葵等远程监控软件、不依赖云端、尽量不侵入 iPad 的前提下：

1. 获取 iPad 当前前台画面；
2. 在 Mac 上显示画面；
3. 点击 Mac 画面中的任意区域；
4. 将点击转换为 iPad 上的鼠标点击；
5. 后续可扩展实体按键、脚踏、语音和自动化控制。

## 当前确定方案

最终目标形态为：Linux 服务器连接 iPad 和 ESP32-S3，提供浏览器 Web 页面进行查看和控制。Linux 服务器需要与 iPad 处于同一地点，能够物理连接采集卡，并能通过蓝牙或 USB 与 ESP32-S3 通信。

正式原型采用：

```text
iPad Air 4
  ├─ USB-C → HDMI → USB 3.0 HDMI 采集卡 → Mac
  └─ 蓝牙 HID ← ESP32-S3

Linux 控制服务
  └─ USB 串口 → ESP32-S3
```

- 画面采集：HDMI 采集卡，Linux 通过 V4L2/GStreamer/FFmpeg 直接读取 UVC 视频流，不依赖 QuickTime。
- Web 访问：Linux 服务通过 WebRTC 向浏览器提供低延迟视频，并通过 WebSocket 接收点击命令。
- 输入控制：Linux 服务通过 USB 串口发送坐标和鼠标事件给 ESP32-S3。
- iPad 控制：ESP32-S3 模拟蓝牙 HID 鼠标，让 iPad 执行移动、点击、长按、拖动等操作。
- 网络：默认不需要互联网、不需要云服务。画面和控制都在本地完成。

## 是否需要购买采集卡

需要。对于确定的 Linux + Web 方案，建议购买一块 HDMI 采集卡作为第一版画面输入设备。QuickTime 仅用于早期验证，不属于最终方案。

建议规格：

- HDMI 输入；
- USB 3.0；
- 1080p60 采集；
- UVC 免驱；
- 明确支持 Linux；
- HDMI 环出可选；
- 不必优先购买 4K 专业型号。

同时需要 USB-C 转 HDMI 适配器和 HDMI 线。第一版建议购买约 80～200 元的 USB 3.0、1080p60 UVC 采集卡，先验证画面采集、延迟和 HDCP 兼容性。

## 当前验证状态

已验证通过：

- Arduino IDE 2.3.10 已安装；
- `esp32 by Espressif Systems` 3.3.11 已安装；
- 开发板为 Seeed XIAO ESP32-S3，实际芯片识别为 ESP32-S3；
- Mac 串口为 `/dev/cu.usbmodem101`（端口号可能因重新插拔变化）；
- iPad 已配对 BLE 设备 `iPad Control Bridge`；
- `/status` 返回 `BLE connected`；
- `/move 30,0` 能使 iPad 鼠标指针移动；
- `/click left` 可执行左键点击。

当前上传使用命令行强制指定 `esp32:esp32:XIAO_ESP32S3`，因为 Arduino IDE 曾错误保留 `XIAO_ESP32C3` 的界面状态。后续操作必须确认 IDE 底部显示 `XIAO_ESP32S3`，不能选择 C3。

## 目录

```text
ipad-control-bridge/
├── README.md
├── firmware/
│   ├── serial_test/serial_test.ino
│   └── ble_mouse_test/ble_mouse_test.ino
├── host/
│   ├── README.md
│   ├── serial_web_bridge.py
│   └── web/index.html
└── docs/
    ├── project-context.md
    └── serial-protocol.md
```

详细背景和方案记录见 [docs/project-context.md](docs/project-context.md)。

## 推荐开发顺序

1. 购买并验证 USB 3.0、1080p60、UVC 免驱 HDMI 采集卡。
2. 在 Mac 上使用 AVFoundation 读取采集卡视频帧。
3. 开发 Mac 控制服务，将视频窗口坐标转换为归一化坐标。
4. 将 `MOVE/DOWN/UP` 协议接入 ESP32 固件。
5. 做坐标校准、长按、拖动和滚动。
6. 将 Mac 原型迁移到 Linux：V4L2/GStreamer + WebRTC + WebSocket。
7. 最后增加 Web 页面、鉴权、急停和本地部署脚本。

## Mac 网页原型

没有采集卡时，可以先启动 [host/serial_web_bridge.py](host/serial_web_bridge.py)，用本地网页验证网页按钮到 iPad 的控制流程：

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host
python3 serial_web_bridge.py
```

然后打开 `http://127.0.0.1:8765`。使用 HDMI 采集卡提供 iPad 画面，网页采用全屏预览加悬浮控制栏；移动、点击和滚动操作通过 USB 串口发送到 ESP32。默认是相对鼠标模式，方向按钮使用“方向步长”，设置面板可调整预览放大倍数。

启动前需要关闭 Arduino IDE 的串口监视器，因为一个串口不能同时被两个程序打开。

## BLE 固件测试

打开 [ble_mouse_test.ino](firmware/ble_mouse_test/ble_mouse_test.ino)，配对名称为 `iPad Control Bridge`。串口波特率为 `115200`，当前支持：

```text
/status
/move x,y
/click left
/scroll n
```

例如：

```text
/status
/move 30,0
/click left
```

BLE 库依赖 `ESP32BLECombo 0.1.0` 和 `NimBLE-Arduino 2.5.1`。详细协议见 [docs/serial-protocol.md](docs/serial-protocol.md)。
