#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/monitor.pid"
LOG_FILE="$DIR/monitor.log"

if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
    echo "⚠️  已在运行中 (PID: $(cat $PID_FILE))"
    exit 0
fi

nohup python3.11 "$DIR/monitor.py" --watch >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "✅ 启动成功 (PID: $!)"
echo "📋 日志: tail -f $LOG_FILE"
