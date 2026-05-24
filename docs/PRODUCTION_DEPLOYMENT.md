# 生产环境部署指南

## 前置要求

- Docker 和 Docker Compose
- 域名和 DNS 配置
- 防火墙开放 80 和 443 端口

## 部署步骤

### 1. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，设置以下关键配置：
```

**必需配置：**
```bash
# 数据库
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=vision_insight
VIA_DATABASE_URL=postgresql+asyncpg://postgres:your_secure_password_here@db:5432/vision_insight

# AI 模型（至少配置一个）
VIA_VLM_PROVIDER=auto
VIA_ZHIPU_API_KEY=your_zhipu_key
# 或
VIA_OPENAI_API_KEY=your_openai_key
# 或
VIA_GEMINI_API_KEY=your_gemini_key

# OCR（推荐配置百度 OCR）
VIA_OCR_PROVIDER=baidu
VIA_BAIDU_OCR_API_KEY=your_baidu_key
VIA_BAIDU_OCR_SECRET_KEY=your_baidu_secret

# 安全配置
VIA_ENABLE_API_KEY_AUTH=true
VIA_API_KEYS=your_api_key_1,your_api_key_2

# CORS（添加你的域名）
VIA_CORS_ORIGINS=["https://imagerecognition.codefromkarl.xyz"]
```

### 2. 初始化 SSL 证书

```bash
# 使脚本可执行
chmod +x scripts/init-ssl.sh

# 运行 SSL 初始化脚本
./scripts/init-ssl.sh imagerecognition.codefromkarl.xyz your-email@example.com
```

### 3. 启动生产环境

```bash
# 使用生产配置启动
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f

# 检查状态
docker compose -f docker-compose.prod.yml ps
```

### 4. 验证部署

```bash
# 检查健康状态
curl -f https://imagerecognition.codefromkarl.xyz/health

# 检查 API 文档
curl -f https://imagerecognition.codefromkarl.xyz/docs

# 测试图片分析
curl -X POST https://imagerecognition.codefromkarl.xyz/api/v1/analyze \
  -H "X-API-Key: your_api_key" \
  -F "file=@test.jpg"
```

## 数据库迁移（从 SQLite）

如果需要从现有 SQLite 迁移数据：

```bash
# 运行迁移脚本
python scripts/migrate-to-postgres.py \
  --sqlite-path data/vision_insight.db \
  --pg-url "postgresql+asyncpg://postgres:your_password@localhost:5432/vision_insight"
```

## 监控和维护

### 查看日志
```bash
# 所有服务日志
docker compose -f docker-compose.prod.yml logs -f

# 特定服务日志
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f nginx
```

### 数据库备份
```bash
# 备份 PostgreSQL
docker compose -f docker-compose.prod.yml exec db pg_dump -U postgres vision_insight > backup_$(date +%Y%m%d).sql

# 恢复备份
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres vision_insight < backup_20260523.sql
```

### SSL 证书续期
证书会自动续期（通过 certbot 服务）。手动续期：
```bash
docker compose -f docker-compose.prod.yml run certbot renew
docker compose -f docker-compose.prod.yml restart nginx
```

## 安全建议

1. **定期更新密码**：定期更换数据库密码和 API 密钥
2. **限制访问**：使用防火墙限制不必要的端口访问
3. **监控日志**：定期检查异常请求和错误日志
4. **备份数据**：定期备份数据库和上传的图片
5. **更新依赖**：定期更新 Docker 镜像和依赖包

## 故障排除

### 服务无法启动
```bash
# 检查日志
docker compose -f docker-compose.prod.yml logs

# 检查端口占用
sudo netstat -tlnp | grep -E ':(80|443) '

# 重启服务
docker compose -f docker-compose.prod.yml restart
```

### SSL 证书问题
```bash
# 检查证书状态
docker compose -f docker-compose.prod.yml run certbot certificates

# 强制续期
docker compose -f docker-compose.prod.yml run certbot renew --force-renewal
```

### 数据库连接问题
```bash
# 检查数据库状态
docker compose -f docker-compose.prod.yml exec db pg_isready

# 连接到数据库
docker compose -f docker-compose.prod.yml exec db psql -U postgres -d vision_insight
```
