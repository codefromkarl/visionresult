# Backend Development Guidelines

> Python / FastAPI / LangGraph 后端开发规范。

---

## Overview

本目录包含 `src/vision_insight/` 的后端开发规范。

**语言**: 文档使用**中文**，代码注释使用**英文**。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | 模块组织和文件布局 | ✅ Active |
| [Database Guidelines](./database-guidelines.md) | PostgreSQL + pgvector 模式 | ✅ Active |
| [Error Handling](./error-handling.md) | 错误类型、降级策略 | ✅ Active |
| [Quality Guidelines](./quality-guidelines.md) | 代码标准、禁止模式 | ✅ Active |
| [Testing Strategy](./testing-strategy.md) | 测试分层、Mock 策略 | ✅ Active |
| [Testing Roadmap](./testing-roadmap.md) | 测试迭代计划 | ✅ Active |
| [Logging Guidelines](./logging-guidelines.md) | 结构化日志、日志级别 | ✅ Active |

---

## Quick Reference

### Tech Stack

- **Runtime**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **AI Pipeline**: LangGraph (多步骤编排)
- **OCR**: PaddleOCR
- **VLM**: Qwen2-VL / OpenAI API / Gemini API
- **Testing**: pytest + pytest-asyncio
- **Linting**: Ruff
- **Type Check**: mypy

### Key Commands

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动开发服务器
uvicorn vision_insight.main:app --reload --port 8000

# Lint + Format
ruff check --fix .
ruff format .

# 类型检查
mypy src/

# 测试
pytest
pytest tests/unit/
pytest tests/integration/
```

### Key Files

| File | Role |
|------|------|
| `src/vision_insight/main.py` | FastAPI 应用入口 |
| `src/vision_insight/core/config.py` | 环境配置 (pydantic-settings) |
| `src/vision_insight/pipeline/graph.py` | LangGraph 分析流程 |
| `src/vision_insight/models/schemas.py` | Pydantic 数据模型 |
| `src/vision_insight/services/__init__.py` | 服务抽象接口 |

### Architecture

```
图片输入 → 预处理 → OCR → VLM分析 → 实体抽取 → 联网检索 → 证据融合 → 报告
```

每个阶段对应一个 Service 接口，通过 LangGraph pipeline 编排。
