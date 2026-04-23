#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/monitor.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  未找到运行记录"
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm "$PID_FILE"
    echo "🛑 已停止 (PID: $PID)"
else
    rm "$PID_FILE"
    echo "⚠️  进程不存在，已清理"
fi
