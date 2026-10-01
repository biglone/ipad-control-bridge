#!/bin/zsh
set -u
PROJECT_HOST="/Users/biglone/workspace/ipad-control-bridge/host"
cd "$PROJECT_HOST" || exit 1
./service.sh stop
read -r "?按回车关闭窗口..."
