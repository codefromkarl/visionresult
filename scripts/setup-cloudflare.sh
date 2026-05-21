#!/bin/bash
# 设置 Cloudflare 资源（D1 数据库 + R2 存储桶）
set -euo pipefail

echo "=== 创建 D1 数据库 ==="
wrangler d1 create vision-insight-db 2>&1 || echo "数据库可能已存在"

echo ""
echo "=== 创建 R2 存储桶 ==="
wrangler r2 bucket create vision-insight-images 2>&1 || echo "存储桶可能已存在"

echo ""
echo "=== 初始化数据库表 ==="
wrangler d1 execute vision-insight-db --file=frontend/schema.sql 2>&1

echo ""
echo "✅ Cloudflare 资源设置完成"
echo ""
echo "请将 D1 database_id 更新到 frontend/wrangler.toml"
echo "然后运行: cd frontend && wrangler pages deploy public"
