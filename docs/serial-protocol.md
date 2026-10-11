# 串口与 BLE 鼠标测试协议

## 当前连接

```text
Mac → USB-C 数据线 → XIAO ESP32-S3 → BLE HID Mouse → iPad Air 4
```

串口默认参数：

- 波特率：`115200`；
- 换行：`New Line`；
- 端口示例：`/dev/cu.usbmodem101`。

端口号可能变化，不应硬编码到最终服务中。

## 当前命令

| 命令 | 作用 | 示例 |
|---|---|---|
| `/status` | 查询 BLE 连接状态 | `/status` |
| `/move x,y` | 移动鼠标相对距离 | `/move 30,0` |
| `/click left` | 左键点击一次 | `/click left` |
| `/key 0-9` | 发送一个数字键 | `/key 5` |
| `/down left` | 按住左键 | `/down left` |
| `/up left` | 释放左键 | `/up left` |
| `/scroll n` | 滚动 | `/scroll -3` |

连接成功时 `/status` 返回：

```text
BLE connected
```

未配对或断开时返回：

```text
BLE not connected; pair the iPad first
```

## 下一版主机协议

当前命令适合人工测试。主机服务应逐步改为机器可解析的协议，例如：

```text
MOVE,0.250,0.400
DOWN,left
UP,left
SCROLL,0,-3
PING
```

建议每条命令都返回一行 ACK 或 ERROR：

```text
ACK,MOVE
ACK,CLICK
ERROR,BLE_DISCONNECTED
```

网页坐标使用 `0.0～1.0` 的归一化坐标，避免采集分辨率变化导致点击偏移：

```text
normalized_x = click_x / video_width
normalized_y = click_y / video_height
```

最终服务应负责：

- 将视频显示区域坐标转换为归一化坐标；
- 根据横竖屏和裁剪区域校准坐标；
- 限制移动距离和点击频率；
- 在串口断开或 BLE 断开时拒绝点击；
- 提供软件急停。
