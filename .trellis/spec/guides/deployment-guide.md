# Deployment Guide

> Visual Insight Agent 部署和验证指南。

---

## Overview

| 组件 | 技术 | 部署方式 |
|------|------|---------|
| Backend API | FastAPI + Uvicorn | Docker / 直接部署 |
| OCR Service | PaddleOCR | 同进程 / 独立服务 |
| VLM Service | Qwen2-VL / API | 本地 GPU / API 调用 |
| Database | PostgreSQL + pgvector | 独立部署 |
| Frontend | Next.js | Vercel / 自托管（计划中） |

---

## 本地开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env

# 启动服务
uvicorn vision_insight.main:app --reload --port 8000

# 访问 API 文档
open http://localhost:8000/docs
```

---

## 验证

### Health Check

```bash
curl http://localhost:8000/health
# 预期: {"status":"ok","version":"0.1.0"}
```

### API 测试

```bash
# 上传图片分析
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@test.jpg"

# 查询报告
curl http://localhost:8000/api/v1/report/{task_id}
```

---

## 部署 Checklist

部署前：

- [ ] `ruff check .` 通过
- [ ] `mypy src/` 通过
- [ ] `pytest` 通过
- [ ] `.env` 配置正确（API keys、数据库）
- [ ] 无敏感数据在代码中

部署后：

- [ ] Health check 返回 200
- [ ] API 文档可访问 (`/docs`)
- [ ] 图片上传测试通过
- [ ] 日志输出正常

---

## Docker 部署（计划中）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
CMD ["uvicorn", "vision_insight.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
