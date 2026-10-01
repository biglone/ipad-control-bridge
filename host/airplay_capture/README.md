# AirPlay 窗口捕获

该工具使用 macOS ScreenCaptureKit 捕获 AirPlay 或 QuickTime 窗口，并将最新帧写入 `host/web/current.jpg`。网页会自动轮询该图片，因此不需要让画面窗口一直遮挡浏览器。

## 编译

```bash
cd /Users/biglone/workspace/ipad-control-bridge/host/airplay_capture
swift build -c release
```

## 运行

先让 iPad 通过 AirPlay 镜像到 Mac，或使用 QuickTime Player 的“文件 → 新建影片录制”并将摄像头选择为 iPad，再执行：

```bash
./.build/release/airplay-capture ../web/current.jpg
```

首次运行需要在 macOS 的“系统设置 → 隐私与安全性 → 屏幕与系统音频录制”中允许终端或该程序访问屏幕。捕获工具找不到窗口时，会打印当前可见窗口列表。
