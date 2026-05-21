# Cloudflare 全家桶部署指南

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Cloudflare 全家桶                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户浏览器                                                      │
│       │                                                         │
│       ▼                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Cloudflare Pages                                        │   │
│   │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│   │ │ 静态前端     │  │ Functions   │  │ Workers AI  │     │   │
│   │ │ HTML/CSS/JS │→│ /api/*      │→│ LLaVA 模型  │     │   │
│   │ └─────────────┘  └─────────────┘  └─────────────┘     │   │
│   │                      │                                  │   │
│   │                      ▼                                  │   │
│   │              ┌─────────────┐  ┌─────────────┐          │   │
│   │              │ D1 数据库   │  │ R2 存储     │          │   │
│   │              │ 分析结果    │  │ 图片文件    │          │   │
│   │              └─────────────┘  └─────────────┘          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   imagerecognition.codefromkarl.xyz                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 优势

| 特性 | 说明 |
|------|------|
| **零服务器** | 不需要维护任何服务器 |
| **全球 CDN** | 自动全球加速 |
| **自动扩展** | 按需扩展，按使用付费 |
| **统一域名** | 前端和 API 在同一域名下 |
| **免费额度** | Workers AI 有免费额度 |

## 部署步骤

### 1. 创建 Cloudflare 资源

```bash
# 运行设置脚本
bash scripts/setup-cloudflare.sh
```

这会创建：
- D1 数据库 (vision-insight-db)
- R2 存储桶 (vision-insight-images)

### 2. 更新配置

将 D1 database_id 更新到 `frontend/wrangler.toml`：

```toml
[[d1_databases]]
binding = "DB"
database_name = "vision-insight-db"
database_id = "你的数据库ID"  # 从 setup 脚本输出获取
```

### 3. 部署到 Cloudflare Pages

```bash
cd frontend
wrangler pages deploy public --project-name=vision-insight
```

### 4. 绑定资源到 Pages

在 Cloudflare Dashboard：
1. 进入 Pages 项目 (vision-insight)
2. Settings → Functions
3. 添加绑定：
   - D1 database → DB
   - R2 bucket → IMAGE_BUCKET
   - Workers AI → AI

## 使用的 Cloudflare 服务

| 服务 | 用途 | 免费额度 |
|------|------|---------|
| **Pages** | 静态前端托管 | 无限 |
| **Functions** | API 端点 | 100k 请求/天 |
| **Workers AI** | LLaVA 图像分析 | 10k 请求/天 |
| **D1** | 分析结果存储 | 5M 读/天 |
| **R2** | 图片存储 | 10GB 存储 |

## 本地开发

```bash
# 启动本地 API 服务器 (用于开发)
uvicorn vision_insight.main:app --reload --port 8001

# 或使用 Cloudflare 本地开发
cd frontend
wrangler pages dev public
```

## 成本估算

| 使用量 | 预估成本 |
|--------|---------|
| 100 次分析/天 | 免费 |
| 1000 次分析/天 | ~$5/月 |
| 10000 次分析/天 | ~$50/月 |

## 局限性

| 局限 | 说明 | 解决方案 |
|------|------|---------|
| Workers AI 模型有限 | 只能用 Cloudflare 提供的模型 | 使用 LLaVA 替代 PaddleOCR |
| 执行时间限制 | 30 秒超时 | 使用 Durable Objects 或 Queues |
| 无 GPU 推理 | 无法运行自定义模型 | 使用 Workers AI 或外部 API |

## 进阶：使用 Queues 处理长时间任务

```javascript
// 生产者：发送到队列
await env.ANALYSIS_QUEUE.send({ taskId, imageKey });

// 消费者：异步处理
export async function queue(batch, env) {
  for (const message of batch) {
    await processImage(env, message.taskId);
  }
}
```
