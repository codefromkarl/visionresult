#!/bin/bash
# Visual Insight Agent — Docker 构建脚本
set -euo pipefail

echo "=== 构建 Docker 镜像 ==="
docker build -t vision-insight:latest .

echo ""
echo "=== 运行容器 ==="
docker run -d \
  --name vision-insight \
  -p 8001:8001 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  --restart unless-stopped \
  vision-insight:latest

echo ""
echo "✅ 容器已启动"
echo "   API: http://localhost:8001"
echo "   Docs: http://localhost:8001/docs"
echo ""
echo "查看日志: docker logs -f vision-insight"
echo "停止容器: docker stop vision-insight"
