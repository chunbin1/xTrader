#!/bin/bash
# xTrader Docker 更新脚本
# 用法：./update.sh

set -e

echo "=== xTrader 更新 $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. 拉取最新代码
echo "[1/4] 拉取最新代码..."
git pull

# 2. 重新构建镜像（不使用缓存，确保依赖最新）
echo "[2/4] 构建镜像..."
docker compose build --no-cache

# 3. 重启容器（先停后起，data 目录挂载不受影响）
echo "[3/4] 重启容器..."
docker compose down
docker compose up -d

# 4. 清理旧镜像，释放磁盘
echo "[4/4] 清理悬挂镜像..."
docker image prune -f

echo ""
echo "✅ 更新完成！容器状态："
docker compose ps
echo ""
echo "查看日志：docker compose logs -f"
