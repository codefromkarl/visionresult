#!/bin/bash
# Visual Insight Agent - 前端预览服务器

set -e

PORT=${1:-8080}
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Visual Insight Agent - 前端预览服务器"
echo ""
echo "📁 服务目录: $DIR"
echo "🌐 访问地址: http://localhost:$PORT"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

cd "$DIR"
python3 -m http.server "$PORT"
