#!/usr/bin/env bash
set -euo pipefail

# Visual Insight Agent — Deploy to Cloudflare Pages
# Usage:
#   bash scripts/deploy.sh          → 部署到 production
#   bash scripts/deploy.sh preview  → 部署到 preview

# 安全地 source ~/.bashrc
if [[ -f ~/.bashrc ]]; then
  set +u
  source ~/.bashrc 2>/dev/null || true
  set -u
fi

# 代理环境绕过
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

export CLOUDFLARE_API_TOKEN="${VIA_DEPLOY_TOKEN:-${CLOUDFRAME_API_KEY:-}}"
if [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
  echo "❌ 请设置 VIA_DEPLOY_TOKEN 或 CLOUDFRAME_API_KEY 环境变量"
  exit 1
fi
export CLOUDFLARE_ACCOUNT_ID="<REDACTED>"

PROJECT="vision-insight"
BRANCH="main"
DIR="frontend/public"

if [[ "${1:-}" == "preview" ]]; then
  BRANCH="preview"
fi

# 寻找 wrangler
WRANGLER=""
if command -v wrangler &>/dev/null; then
  WRANGLER="$(command -v wrangler)"
else
  WRANGLER="npx wrangler"
fi

echo "🚀 Deploying to Cloudflare Pages..."
echo "   Project: $PROJECT"
echo "   Branch:  $BRANCH"
echo "   Source:  $DIR"
echo ""

$WRANGLER pages deploy "$DIR" \
  --project-name="$PROJECT" \
  --branch="$BRANCH"

echo ""
echo "✅ 部署完成!"
echo "   Production: https://vision-insight.pages.dev"
echo "   Custom:     https://imagerecognition.codefromkarl.xyz"

# ─── 部署后健康检查 ───────────────────────────────────────

echo ""
echo "🔍 等待 CDN 缓存更新 (5s)..."
sleep 5

if [[ -f "scripts/health-check.sh" ]]; then
  bash scripts/health-check.sh || {
    echo "⚠️  健康检查失败，请手动验证"
    exit 1
  }
fi
