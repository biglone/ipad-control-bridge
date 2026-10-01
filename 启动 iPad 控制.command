#!/bin/zsh
set -u
PROJECT_HOST="/Users/biglone/workspace/ipad-control-bridge/host"
cd "$PROJECT_HOST" || exit 1
./service.sh start
echo
echo "网页地址：http://127.0.0.1:8765/"
echo "可以关闭这个窗口，服务会继续运行。"
read -r "?按回车关闭窗口..."
