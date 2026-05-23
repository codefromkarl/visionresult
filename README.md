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
| OCR | Baidu OCR / Tesseract / PaddleOCR | 文字提取（中/日/英），支持多引擎降级 |
| VLM | Zhipu / OpenAI / Gemini / 降级模式 | 场景理解，支持 provider fallback |
| 实体抽取 | LLM + 规则降级 | 结构化信息提取 |
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

# 启用 verbose 模式（包含推理链路）
curl -X POST http://localhost:8000/api/v1/analyze?verbose=true \
  -F "file=@test.jpg"

# 获取报告（包含推理链路）
curl http://localhost:8000/api/v1/report/{task_id}?include_trace=true
```

## 技术栈

- **后端**: Python 3.11+ / FastAPI / LangGraph
- **OCR**: Baidu OCR / Tesseract / PaddleOCR（按配置自动降级）
- **VLM**: Zhipu GLM-4V / OpenAI API / Gemini API / 降级模式
- **前端**: 静态 HTML/CSS/JavaScript（支持上传、进度、报告、推理链路可视化）
- **数据库**: SQLite（当前本地持久化）；PostgreSQL + pgvector 为后续扩展方向

## 降级策略

系统现在以“可用优先、明确降级”为原则：

1. **OCR fallback**：优先使用配置的 OCR provider；Baidu 未配置或 provider 失败时，可回退到 Tesseract / PaddleOCR；所有 OCR 都不可用时返回空 OCR 结果，但 pipeline 继续执行。
2. **VLM fallback**：`VIA_VLM_PROVIDER=auto` 时按 Zhipu → OpenAI → Gemini 选择可用 provider；当前 provider 失败或限流时尝试下一个；全部不可用时返回明确的 `unknown` 场景和“不瞎猜”的说明。
3. **实体抽取 fallback**：无 LLM key 时使用规则抽取，保留 VLM 地点猜测与高置信 OCR 文本。
4. **证据链优先**：结论必须带来源、置信度和推理策略；verbose 模式会记录 Pipeline Trace。

## 设计原则

1. **宁可不确定，也不要瞎猜** — 诚实表达不确定性
2. **证据链优先** — 每个推断必须有依据
3. **规则 + LLM 混合** — 不让 LLM 直接决定一切

## 推理链路功能

系统支持 **Verbose 模式**，可以记录并展示完整的推理过程：

### 功能特性

1. **Pipeline 执行详情** — 记录每个阶段的输入/输出、耗时、关键发现
2. **思考链条** — 展示证据融合的推理过程（规则匹配 / LLM推理）
3. **调用证据链** — 可视化证据如何被加权和融合

### 使用方法

```bash
# API 调用时启用 verbose 模式
curl -X POST http://localhost:8000/api/v1/analyze?verbose=true \
  -F "file=@test.jpg"

# 获取包含推理链路的报告
curl http://localhost:8000/api/v1/report/{task_id}?include_trace=true
```

### 前端可视化

前端界面支持：
- 勾选「启用详细推理链路」复选框
- 点击「🔍 推理链路」按钮查看完整推理过程
- 时间线展示每个 Pipeline 阶段
- 卡片式展示每个结论的推理策略和证据

### 返回数据结构

```json
{
  "pipeline_trace": {
    "steps": [
      {
        "stage_name": "ocr",
        "status": "success",
        "duration_ms": 150,
        "input_summary": "Image 1920x1080",
        "output_summary": "5 text regions detected",
        "key_findings": ["Text: 'Shibuya'", "Text: '109'"]
      }
    ],
    "reasoning_traces": [
      {
        "conclusion_category": "location",
        "conclusion_statement": "拍摄地点: 东京涩谷",
        "final_probability": 0.85,
        "strategy_used": "rule",
        "steps": [
          {
            "action": "rule_match",
            "description": "High confidence match (>0.8)",
            "confidence_before": 0.95,
            "confidence_after": 0.85
          }
        ]
      }
    ],
    "total_duration_ms": 500
  }
}
```

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
├── frontend/          # 静态前端页面与 Cloudflare 部署文件
├── tests/             # 单元、集成、质量守卫、E2E 测试
├── configs/           # 配置文件
└── docs/              # 文档
```

## License

MIT
