# 技术栈研究与决策

## 后端框架

### 选择: FastAPI
- 异步支持好，适合 AI 推理任务
- 自动生成 OpenAPI 文档
- 类型安全（Pydantic v2）
- 社区活跃，文档完善

### 备选: Flask / Django
- Flask: 缺少异步原生支持
- Django: 过重，不需要 ORM/admin

## AI Pipeline 编排

### 选择: LangGraph
- 专为多步骤 AI pipeline 设计
- 支持条件分支、循环、人工介入
- 与 LangChain 生态兼容
- 状态管理清晰

### 备选: Celery + Redis
- 更适合通用异步任务
- 缺少 AI pipeline 的语义抽象

## OCR

### 选择: PaddleOCR
- 中文识别最强
- 日文、韩文支持好
- 工程成熟，模型丰富
- 支持版面分析

### 备选: Tesseract
- 中文识别效果差
- 配置复杂

## 视觉语言模型 (VLM)

### MVP: API 方案（OpenAI GPT-4V / Gemini Pro Vision）
- 快速验证
- 无需 GPU
- 效果好

### 进阶: Qwen2-VL 本地部署
- 中文理解强
- 可控性高
- 无 API 费用

### 备选: LLaVA / InternVL
- Qwen2-VL 综合能力更强

## 实体抽取

### 选择: LLM 抽取 + spaCy 辅助
- LLM 处理复杂实体（地名、品牌、建筑）
- spaCy 处理基础 NER（人名、组织）
- 混合方案兼顾准确性和成本

## 向量数据库

### MVP: pgvector
- 与 PostgreSQL 集成
- 运维简单
- 足够 MVP 阶段使用

### 进阶: Milvus
- 大规模向量搜索
- 分布式支持

## 前端

### 选择: Next.js + React
- SSR/SSG 支持
- API Routes 可做 BFF
- 生态成熟
- 部署简单（Vercel）

## 图像处理

### 选择: Pillow + OpenCV
- Pillow: EXIF 提取、格式转换、压缩
- OpenCV: 图像增强、预处理
- 两者互补

## 证据融合策略

### "规则 + LLM" 混合
- 高置信度信号（OCR 精确匹配地标）→ 规则直接判定
- 中等置信度 → LLM 辅助推理
- 低置信度 → 标记为不确定
- 关键：不让 LLM 独自决定一切
