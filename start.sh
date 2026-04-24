#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/monitor.pid"
LOG_FILE="$DIR/monitor.log"

# 杀掉所有正在运行的 monitor.py 进程（无论是否在 pid 文件中记录）
EXISTING=$(pgrep -f "python.*monitor\.py" 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo "🔄 发现已有进程 ($EXISTING)，先停止..."
    echo "$EXISTING" | xargs kill 2>/dev/null
    sleep 1
fi
rm -f "$PID_FILE"

nohup python3.11 "$DIR/monitor.py" --watch >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "✅ 启动成功 (PID: $!)"
echo "📋 日志: tail -f $LOG_FILE"
