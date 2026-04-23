#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/monitor.pid"
LOG_FILE="$DIR/monitor.log"

if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
    echo "🟢 运行中 (PID: $(cat $PID_FILE))"
    echo ""
    echo "── 最近10条日志 ──"
    tail -10 "$LOG_FILE"
else
    echo "🔴 未运行"
fi
