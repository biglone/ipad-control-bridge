# Mac 串口网页原型

这是没有 HDMI 采集卡时使用的第一版主机端验证程序。它可以捕获 AirPlay 或 QuickTime 的 iPad 画面，并提供一个本地网页，将按钮操作转成 ESP32 BLE 鼠标命令。

## 启动

推荐使用统一服务脚本：

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host
./service.sh start
```

Mac 本机打开 <http://127.0.0.1:8765>；手机与 Mac 连接同一 Wi‑Fi 后，打开启动脚本输出的局域网地址，例如
`http://192.168.1.23:8765`。网页服务默认监听局域网，若只允许本机访问，可设置
`IPAD_BRIDGE_HOST=127.0.0.1` 后再启动。
如果 `8765` 已被其他服务占用，可用 `IPAD_BRIDGE_PORT=28765 ./service.sh start` 改用其他端口。

常用命令：

```bash
./service.sh status   # 查看采集、网页和 ESP32 状态
./service.sh restart  # 重新启动采集和网页服务
./service.sh stop     # 停止服务
./service.sh logs     # 查看日志文件位置
```

脚本会自动寻找 `UGREEN 25854`，如果找不到采集卡会停止并写入 `logs/capture.log`，不会误用 Mac 摄像头。网页日志位于 `logs/web.log`。

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host
python3 serial_web_bridge.py
```

然后打开 <http://127.0.0.1:8765>；手机访问时使用 Mac 的局域网 IP 加端口 `8765`。

启动前请关闭 Arduino IDE 串口监视器，否则串口会被占用。iPad 继续保持与 `iPad Control Bridge` 的蓝牙连接。

## 验证

1. 在 Mac 上用 AirPlay 镜像或 QuickTime 显示 iPad 画面；
2. 打开本网页；
3. 点击“右移 →”，观察 iPad 指针移动；
4. 点击“左键点击”，观察 iPad 执行点击；
5. 用“刷新状态”确认 `BLE 已连接`。

网页画面区域支持单指操作：

- 单指点击：按下后立即释放；
- 单指拖动：按住并移动，网页会连续发送按下、相对移动、释放命令，可用于翻页和页面内滚动；
- 从画面底部向上拖动：尝试触发 iPad 的底部系统手势；
- “底部上滑”：发送一条固定距离的上滑测试动作。
- “回到首页（⌘H）”：通过 BLE 键盘快捷键发送 iPadOS 的 `Command + H`，通常比鼠标底部上滑可靠。

网页现在使用全屏视频预览作为主界面，控制按钮以悬浮工具栏叠加在画面底部。默认是相对鼠标模式：拖动画面发送相对移动，方向按钮发送方向移动，左键按钮点击当前 iPad 光标位置。方向步长只影响四个方向按钮；滚轮步长独立配置，默认 400；设置面板中的画面放大只影响预览显示。

### 锁屏数字输入

部分 iPad 在 HDMI 外接画面中不会显示锁屏数字键盘，只输出密码圆点和背景画面。网页会在视频画面下方叠加“数字触摸键”，点击 0～9 会通过 ESP32 的 BLE HID 键盘发送对应数字。首次使用或修改固件后，需要重新烧录 `firmware/ble_mouse_test/ble_mouse_test.ino`；如果 iPad 仍不响应，请在蓝牙设置中忽略旧的 `iPad Control Bridge` 后重新配对。

预览默认 1:1 显示，可在设置面板中调整画面放大 1.0～2.0 倍。采集脚本不再把 1080p 输入缩小到 1280 宽度，优先保留采集卡原始分辨率；如果采集卡只输出 1280×720，则放大只能改善显示比例，不能增加实际细节。

移动命令现在使用串行队列发送，不会因为前一条命令尚未返回而丢失连续滑动事件。ESP32 现在同时模拟 BLE 鼠标和键盘；首次刷入组合 HID 固件后，若 iPad 没有响应，请在蓝牙设置中忽略旧的 `iPad Control Bridge`，再重新配对。

当前网页不再提供不稳定的视频光标识别和画面绝对坐标映射，避免误导。若未来要支持绝对坐标点击，需要单独实现闭环光标追踪或绝对坐标 HID。

## QuickTime 窗口捕获

QuickTime 验证推荐使用窗口捕获工具，不需要让 QuickTime 一直位于前台：

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host
swiftc quicktime_capture.swift -o quicktime-capture
./quicktime-capture web/current.jpg
```

保持 QuickTime 的“新建影片录制”窗口打开，然后切换到浏览器即可。捕获程序会持续寻找 QuickTime 窗口并更新网页画面。

## HDMI 采集卡直连

Mac 识别到采集卡后，可以绕过 QuickTime，直接让 FFmpeg 读取 UVC 视频设备：

```bash
ffmpeg -f avfoundation -list_devices true -i ''
```

脚本会按名称自动寻找 `UGREEN 25854`，直接运行：

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host
./capture_card_ffmpeg.sh
```

如果手动指定编号，脚本会先确认该编号确实对应 UGREEN 采集卡，不会误打开 Mac 摄像头：

```bash
./capture_card_ffmpeg.sh 1
```

采集脚本会持续更新 `web/current.jpg`，网页服务会自动显示最新画面。当前网页控制接口不变，仍然通过 ESP32 BLE HID 发送鼠标、键盘和滑动操作。
