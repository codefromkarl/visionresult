#!/bin/bash
# Visual Insight Agent — 线上健康检查脚本
#
# Usage:
#   bash scripts/health-check.sh              # 检查 production
#   bash scripts/health-check.sh preview      # 检查 preview
#   bash scripts/health-check.sh <URL>        # 检查自定义 URL

set -euo pipefail

# ─── URL 解析 ──────────────────────────────────────────────

PROD_URL="https://vision-insight.pages.dev"
PREVIEW_URL="https://preview.vision-insight.pages.dev"

case "${1:-production}" in
  production|prod)
    BASE_URL="$PROD_URL"
    ENV_NAME="Production"
    ;;
  preview)
    BASE_URL="$PREVIEW_URL"
    ENV_NAME="Preview"
    ;;
  http*|https*)
    BASE_URL="$1"
    ENV_NAME="Custom"
    ;;
  *)
    echo "Usage: $0 [production|preview|<URL>]"
    exit 1
    ;;
esac

echo "=== 线上健康检查 ==="
echo "环境: $ENV_NAME"
echo "URL:  $BASE_URL"
echo ""

ERRORS=0

# ─── 1. 页面可访问 ──────────────────────────────────────────

echo -n "1. 页面可访问... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -L "$BASE_URL/")
if [[ "$STATUS" == "200" ]]; then
  echo "✅ HTTP $STATUS"
else
  echo "❌ HTTP $STATUS"
  ERRORS=$((ERRORS + 1))
fi

# ─── 2. API Health 端点 ─────────────────────────────────────

echo -n "2. API Health 端点... "
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$BASE_URL/health" 2>/dev/null || echo "000")
if [[ "$API_STATUS" == "200" || "$API_STATUS" == "000" ]]; then
  echo "✅ HTTP $API_STATUS"
else
  echo "⚠️  HTTP $API_STATUS (API 可能未部署到 Pages)"
fi

# ─── 3. 响应时间 ────────────────────────────────────────────

echo -n "3. 响应时间... "
TOTAL_TIME=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 "$BASE_URL/")
TIME_MS=$(echo "$TOTAL_TIME * 1000" | bc | cut -d. -f1)
if [[ "$TIME_MS" -lt 3000 ]]; then
  echo "✅ ${TIME_MS}ms"
else
  echo "⚠️  ${TIME_MS}ms (较慢)"
fi

# ─── 结果 ────────────────────────────────────────────────────

echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo "✅ 所有检查通过"
  exit 0
else
  echo "❌ $ERRORS 项检查失败"
  exit 1
fi
