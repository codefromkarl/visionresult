# 生产环境部署指南

## 架构选择

| 方案 | 适用场景 | 成本 | 复杂度 |
|------|---------|------|--------|
| **Railway** | 快速部署，免运维 | 免费额度 + $5/月起 | ⭐ 简单 |
| **Render** | 类似 Railway | 免费额度 + $7/月起 | ⭐ 简单 |
| **VPS + Docker** | 完全控制 | $5/月起 | ⭐⭐ 中等 |
| **AWS/GCP** | 企业级 | 按量付费 | ⭐⭐⭐ 复杂 |

---

## 方案 1: Railway（推荐新手）

### 步骤

1. **注册 Railway**: https://railway.app

2. **连接 GitHub 仓库**

3. **配置环境变量**:
   ```
   VIA_OPENAI_API_KEY=sk-...
   VIA_VLM_PROVIDER=openai
   VIA_OCR_LANG=ch
   ```

4. **部署**: Railway 自动检测 Python 项目并部署

5. **获取域名**: Railway 提供 `*.up.railway.app` 域名

6. **更新前端**: 在前端 API 配置中输入 Railway 域名

---

## 方案 2: VPS + Docker（推荐生产）

### 准备 VPS

```bash
# 1. 购买 VPS (DigitalOcean, Vultr, 阿里云等)
# 最低配置: 1 CPU, 1GB RAM, 25GB SSD

# 2. SSH 连接
ssh root@your-server-ip

# 3. 安装 Docker
curl -fsSL https://get.docker.com | sh
```

### 部署步骤

```bash
# 1. 克隆代码
git clone https://github.com/your-repo/visionresult.git
cd visionresult

# 2. 配置环境变量
cp .env.example .env
nano .env  # 填入 API keys

# 3. 使用 Docker Compose 启动
docker-compose up -d

# 4. 检查状态
docker-compose ps
docker-compose logs -f api

# 5. 验证
curl http://localhost:8001/health
```

### 配置域名和 SSL

```bash
# 安装 Certbot
apt install certbot python3-certbot-nginx

# 配置 SSL
certbot --nginx -d imagerecognition.codefromkarl.xyz

# 自动续期
crontab -e
# 添加: 0 0 * * * certbot renew --quiet
```

---

## 方案 3: 单独部署 API（前后端分离）

### 前端: Cloudflare Pages（已有）
- URL: https://imagerecognition.codefromkarl.xyz

### 后端: Railway/Render/VPS
- URL: https://api-vision.railway.app (示例)

### 配置前端连接后端

在前端页面底部 API 配置框输入后端 URL，或修改代码：

```javascript
const API_BASE = 'https://api-vision.railway.app';
```

---

## 环境变量说明

```bash
# 必需
VIA_OPENAI_API_KEY=sk-...        # OpenAI API Key
VIA_VLM_PROVIDER=openai          # VLM 提供商

# 可选
VIA_OCR_LANG=ch                  # OCR 语言
VIA_GOOGLE_API_KEY=...           # Google 搜索
VIA_BING_API_KEY=...             # Bing 搜索
VIA_DEBUG=false                  # 生产环境关闭 debug
```

---

## 监控和维护

### 健康检查

```bash
# 检查 API 状态
curl https://your-api-url/health

# 检查容器状态
docker-compose ps

# 查看日志
docker-compose logs -f api
```

### 备份数据

```bash
# 备份分析记录
cp -r data/ backup/

# 定期备份 (crontab)
0 2 * * * cd /path/to/visionresult && tar -czf backup/data-$(date +%Y%m%d).tar.gz data/
```

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并部署
docker-compose down
docker-compose up -d --build
```

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 405 Method Not Allowed | 前端直接访问静态托管 | 配置 API URL 指向后端 |
| 404 Not Found | API 路由未注册 | 检查 FastAPI 启动日志 |
| 500 Internal Server Error | 代码错误 | 查看 docker-compose logs |
| 连接超时 | 网络问题 | 检查防火墙/安全组 |
| OCR 失败 | PaddleOCR 未安装 | 检查 Docker 构建日志 |
