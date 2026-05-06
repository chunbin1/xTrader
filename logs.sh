#!/bin/bash
# 查看 xTrader 日志
# 用法：./logs.sh [行数]  默认实时跟踪，Ctrl+C 退出

LINES=${1:-50}

docker compose logs --tail="$LINES" -f
