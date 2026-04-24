#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/monitor.pid"

KILLED=0

# 先按 pid 文件停
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "🛑 已停止 (PID: $PID)"
        KILLED=1
    fi
    rm -f "$PID_FILE"
fi

# 再用 pgrep 兜底，杀掉漏网的同名进程
REMAINING=$(pgrep -f "python.*monitor\.py" 2>/dev/null)
if [ -n "$REMAINING" ]; then
    echo "$REMAINING" | xargs kill 2>/dev/null
    echo "🛑 清理残留进程 ($REMAINING)"
    KILLED=1
fi

[ "$KILLED" -eq 0 ] && echo "⚠️  没有运行中的进程"
