# Visual Insight Agent

多模态图片分析系统 — 视觉分析 + 证据链推理

## 核心能力

用户上传图片 → 自动分析 → 联网补充 → 结构化视觉调查报告

### 输出示例

```markdown
# 图片分析报告

## 场景
日本商业街夜景

## 地点推测
东京涩谷（82%）

## 依据
- 日文招牌
- 涩谷109建筑
- JR地铁标志

## 时间推测
- 夜晚
- 冬季

## OCR 文字
- Shibuya (98%)
- 109 (95%)
```

## 架构

```
图片输入 → 预处理 → OCR → VLM分析 → 实体抽取 → 联网检索 → 证据融合 → 报告
```

### 核心模块

| 模块 | 技术 | 作用 |
|------|------|------|
| OCR | PaddleOCR | 文字提取（中/日/英） |
| VLM | Qwen2-VL / OpenAI / Gemini | 场景理解 |
| 实体抽取 | spaCy / LLM | 结构化信息提取 |
| 联网检索 | Google / Bing / Wikipedia | 信息验证 |
| 证据融合 | 规则 + LLM | 多源证据加权 |
| Pipeline | LangGraph | 多步骤编排 |

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API keys

# 启动服务
uvicorn vision_insight.main:app --reload --port 8000

# 上传图片分析
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@test.jpg"
```

## 技术栈

- **后端**: Python 3.11+ / FastAPI / LangGraph
- **OCR**: PaddleOCR
- **VLM**: Qwen2-VL (本地) / OpenAI API / Gemini API
- **前端**: React + Next.js (计划中)
- **数据库**: PostgreSQL + pgvector

## 设计原则

1. **宁可不确定，也不要瞎猜** — 诚实表达不确定性
2. **证据链优先** — 每个推断必须有依据
3. **规则 + LLM 混合** — 不让 LLM 直接决定一切

## 项目结构

```
visionresult/
├── src/vision_insight/
│   ├── api/           # FastAPI 路由
│   ├── core/          # 配置、依赖注入
│   ├── models/        # Pydantic 数据模型
│   ├── pipeline/      # LangGraph 分析流程
│   ├── services/      # 各服务实现
│   │   ├── ocr/       # PaddleOCR
│   │   ├── vlm/       # 视觉语言模型
│   │   ├── entity/    # 实体抽取
│   │   ├── search/    # 联网检索
│   │   ├── evidence/  # 证据融合
│   │   └── report/    # 报告生成
│   └── utils/         # 工具函数
├── frontend/          # Next.js 前端（计划中）
├── tests/             # 测试
├── configs/           # 配置文件
└── docs/              # 文档
```

## License

MIT
