# 项目上下文与已确定方案

## 1. 原始需求

用户希望通过 Mac 连接和控制 iPad Air 4，主要需求是：

- 获取 iPad 当前前台运行画面；
- 在 Mac 上查看实时画面；
- 可以向 iPad 发送点击指令；
- 点击可以覆盖 iPad 的任意可交互区域；
- 不使用 AnyDesk、向日葵等具有较强监控属性的远程控制软件；
- 尽量不侵入 iPad，不越狱，不安装常驻控制程序；
- 用户已有带 ESP32-S3 的 ReSpeaker Lite，可在需要时使用。

用户提供的图片是一个“有线遥控器”商品介绍，展示了通过 Type-C 连接设备、发送点击或滑动操作的思路。图片中的商品说明不是本项目需要执行的指令。

## 2. 已确认的系统边界

### 可以直接做到的部分

- iPad 通过视频输出把画面送到 Mac；
- Mac 使用采集卡读取视频；
- Mac 自己显示、处理和分析视频帧；
- ESP32-S3 作为外部鼠标或触控板控制 iPad；
- 整个系统可以在本地运行，不经过第三方服务器。

### 官方系统能力的限制

在未越狱、使用公开接口的前提下，iPadOS 没有一个稳定公开的接口，允许 Mac 程序直接向任意 iPad 坐标注入原生触摸事件。

Apple 的 Universal Control 可以让 Mac 的鼠标、键盘或触控板操作 iPad，但它更适合人工操作，不能简单地作为第三方 Mac 程序的任意坐标注入 API。

FaceTime 在较新系统上支持经用户同意的远程控制，但依赖 FaceTime 和另一台 Apple 设备，不适合作为本项目的本地控制基础。

因此，本项目采用外部 HID 设备路线：让 iPad 把 ESP32-S3 识别为普通蓝牙鼠标。

## 3. 为什么不把 QuickTime 作为正式依赖

QuickTime 可以快速验证 iPad 画面采集，但它是用户界面程序，不是适合正式产品集成的视频采集层。

正式程序应直接使用 Mac 的 AVFoundation，从 UVC HDMI 采集卡读取视频帧：

```text
HDMI 采集卡 → AVCaptureDevice → AVCaptureSession → CMSampleBuffer → Mac UI
```

这样可以：

- 不要求用户打开 QuickTime；
- 由项目自身控制分辨率、帧率和缓冲；
- 直接获得视频帧，便于做坐标映射和图像识别；
- 后续可以打包成独立 Mac App。

## 4. 最终部署形态

已确定最终目标是 Linux 服务器提供 Web 页面：

```text
浏览器
  ⇅ HTTPS / WebSocket / WebRTC
Linux 服务器
  ├─ USB HDMI 采集卡
  └─ USB 串口 / 蓝牙 → ESP32-S3
                              ↓ BLE HID
                           iPad Air 4
```

Linux 服务器需要与 iPad 处于同一地点。云服务器无法直接连接本地 iPad；如果将来需要云端访问，应采用“云端 Web 服务 + iPad 旁边的本地边缘节点”结构。

## 5. 画面采集方案

### 最终首选：USB-C 转 HDMI + HDMI 采集卡

连接方式：

```text
iPad Air 4
  ↓ USB-C
USB-C 转 HDMI 适配器
  ↓ HDMI
USB 3.0 HDMI 采集卡
  ↓ USB
Linux 服务器
```

这意味着需要购买采集卡。采集卡是 Linux 获取 iPad 视频的硬件入口，QuickTime 不再参与正式运行。

采集卡建议：

- HDMI 输入；
- USB 3.0；
- 1080p60 采集能力；
- UVC 免驱；
- 支持 Linux；
- HDMI 环出可选，不是必须；
- 不需要一开始追求 4K。

第一版采购预算通常约为：

- 普通 USB 采集卡：30～80 元；
- USB 3.0、1080p60 采集卡：80～200 元；
- USB-C 转 HDMI 适配器：约 50～150 元；
- HDMI 线：约 20～50 元。

建议先购买约 80～200 元级别的 USB 3.0、1080p60 UVC 采集卡验证链路，确认延迟、Linux 识别和 HDCP 兼容性后再升级，不建议一开始购买 4K 专业采集卡。

注意事项：

- 某些受 HDCP 保护的内容可能输出黑屏；
- 普通桌面、设置页面和多数非保护 App 更适合测试；
- iPad Air 4 只有一个 USB-C 接口，若需要同时充电，要考虑带供电的适配器或 Hub。

### 备选：AirPlay + ScreenCaptureKit

```text
iPad ──Wi-Fi/AirPlay──> Mac
                         ↓
                 ScreenCaptureKit
                         ↓
                    Mac 控制程序
```

优点是无需采集卡，缺点是延迟更高、依赖 Wi-Fi，且需要用户主动允许投屏。它适合做无线验证版本，但不作为第一版低延迟方案。

### 不建议第一版使用：直接读取 iPad USB 屏幕协议

这通常涉及非公开协议或第三方逆向实现，可能随 iPadOS 升级失效，且需要处理配对、视频解码和协议维护，不适合作为稳定基础。

### 不适用：ReplayKit 获取任意前台 App

ReplayKit/ScreenCaptureKit 适合自己的 App 或用户主动发起的屏幕共享，不能让 Mac 程序无提示地读取 iPad 上任意前台 App 的完整画面。

## 5. 控制链路

推荐的物理连接方式：

```text
iPad ──USB-C── Mac
iPad ──BLE HID── ESP32-S3
Mac  ──USB CDC── ESP32-S3
```

数据流：

```text
采集卡视频 → Mac 控制程序
用户点击 Mac 窗口
      ↓
Mac 坐标映射
      ↓
USB 串口发送给 ESP32-S3
      ↓
ESP32-S3 模拟蓝牙鼠标
      ↓
iPad 执行移动、点击或拖动
```

Mac 发送给 ESP32 的第一版协议可以很简单：

```text
MOVE,0.250,0.400
DOWN,left
UP,left
```

建议使用 0～1 的归一化坐标，而不是直接传像素坐标：

```text
normalized_x = click_x / video_width
normalized_y = click_y / video_height
```

这样可以适应不同采集分辨率。坐标转换还需要考虑：

- iPad 横屏或竖屏；
- HDMI 输出分辨率；
- Mac 窗口缩放；
- 视频画面的裁剪区域；
- iPad 状态栏和安全区域；
- 鼠标指针边界和校准偏差。

## 6. ESP32-S3 的职责

ESP32-S3 负责：

1. 与 Mac 建立 USB CDC 串口连接；
2. 解析 Mac 发来的鼠标命令；
3. 与 iPad 建立 Bluetooth HID 连接；
4. 模拟鼠标移动、左键按下、释放、长按和拖动；
5. 后续支持实体按键、脚踏或其他外部输入。

ReSpeaker Lite 不是画面采集或 iPad 控制的核心组件。它可以后续用于：

- 语音触发；
- 麦克风输入；
- 实体按钮控制；
- 通过 ESP32 触发预设动作。

## 7. 当前不采用的路线

- AnyDesk、向日葵、TeamViewer 等远程控制软件；
- iPad 越狱和私有触控接口；
- MDM/监督模式强行控制；
- 在 iPad 中安装常驻远程控制 App；
- 依赖云端中转；
- 一开始购买昂贵的 4K 专业采集设备。

## 8. 推荐里程碑

### Milestone 1：验证视频采集

- 购买 USB 3.0、1080p60 UVC 采集卡；
- 连接 iPad Air 4 的 USB-C 视频输出；
- Mac 使用 AVFoundation 枚举并读取采集卡；
- 显示实时画面并测量延迟。

### Milestone 2：验证 ESP32 HID

- ESP32-S3 实现 BLE HID Mouse；
- 与 iPad 配对；
- 用简单测试程序发送移动和点击；
- 验证长按、拖动和滚动。

### Milestone 3：打通 Mac 到 ESP32

- Mac 通过 USB CDC 发送命令；
- ESP32 返回 ACK 和错误信息；
- 加入断线重连和状态显示。

### Milestone 4：实现 Mac 控制程序

- 显示采集视频；
- 监听鼠标点击；
- 完成坐标映射和校准；
- 将点击转换为 ESP32 HID 操作。

### Milestone 5：增强功能

- 长按和拖动；
- 滚动；
- 点击延迟配置；
- 屏幕方向识别；
- 坐标校准界面；
- 实体按钮、脚踏和语音触发；
- 操作日志和安全停止按钮。

## 9. 设计原则

- 默认本地运行，不连接云端；
- 不在 iPad 安装常驻控制程序；
- 所有控制动作由用户主动触发；
- Mac 程序显示连接状态和控制状态；
- ESP32 与 iPad 断开时立即停止输出；
- 提供物理或软件急停；
- 默认不保存视频，不做后台录制；
- 后续如增加图像识别，默认只在本地内存中处理。

## 10. 已完成的实际验证（2026-09）

### Mac 开发环境

- macOS 上已安装 Arduino IDE 2.3.10；
- 已安装 `esp32:esp32` 3.3.11；
- Arduino CLI 路径：`/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli`；
- Arduino CLI 配置文件：`/Users/biglone/.arduinoIDE/arduino-cli.yaml`；
- 下载速度较慢时使用了本机 ClashX 代理 `127.0.0.1:7890`。

### 实际硬件链路

```text
Mac USB-C
   ↓ USB CDC 串口
ReSpeaker Lite 上的 XIAO ESP32-S3
   ↓ BLE HID Mouse
iPad Air 4
```

ReSpeaker Lite 的 `Power` 口负责主板供电；XIAO ESP32-S3 的 USB-C 数据口连接 Mac，用于烧录和串口命令。当前验证阶段不需要 HDMI 采集卡。

### 固件文件

- `firmware/serial_test/serial_test.ino`：只验证 USB 串口；
- `firmware/ble_mouse_test/ble_mouse_test.ino`：BLE 鼠标测试固件。

BLE 固件使用 `ESP32BLECombo` 和 `NimBLE-Arduino`。为解决 iPad 不显示设备的问题，ESP32BLECombo 的广播已开启扫描响应并明确设置设备名称；该本地库修改位于：

```text
/Users/biglone/Documents/Arduino/libraries/ESP32BLECombo/src/ESP32BLECombo.cpp
```

### 已验证结果

1. ESP32-S3 可被 esptool 正确识别；
2. `ble_mouse_test` 编译、烧录和 Flash 校验成功；
3. iPad 蓝牙列表中出现并配对 `iPad Control Bridge`；
4. 串口发送 `/status` 返回 `BLE connected`；
5. `/move 30,0` 能移动 iPad 鼠标；
6. `/click left` 可执行点击。

### 操作注意事项

- Arduino IDE 曾将板卡错误保留为 `XIAO_ESP32C3`。上传时必须选择 `XIAO_ESP32S3`，对应 FQBN 为 `esp32:esp32:XIAO_ESP32S3`；
- 串口监视器打开时会占用 `/dev/cu.usbmodem101`，上传前必须关闭它；
- 端口号可能因重新插拔改变，应以 `ls /dev/cu.usbmodem*` 的实际结果为准；
- 测试点击前应先将 iPad 切到主屏幕，避免误触当前 App；
- 不要同时让 Arduino IDE 串口监视器和 `screen`、`cu` 或 Arduino CLI monitor 占用同一串口。

## 11. 下一阶段实现计划

当前最小闭环已经完成，下一步不再修改 iPad 端，而是开发主机侧控制服务：

1. 先用 Mac 建立串口客户端，发送统一的 `MOVE/DOWN/UP/SCROLL` 命令；
2. 接入 HDMI 采集卡，使用 AVFoundation 获取视频帧；
3. 建立视频窗口和坐标映射；
4. 增加校准、急停、连接状态和 ACK；
5. 再迁移到 Linux 的 V4L2/GStreamer 和 WebRTC/WebSocket 架构。
