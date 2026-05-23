# Visual Insight Agent - 领域术语表

## 核心领域概念

### 分析流程 (Analysis Pipeline)
图片分析的完整流程，包含多个阶段：预处理 → OCR → VLM分析 → 实体抽取 → 联网检索 → 证据融合 → 报告生成

### 证据融合 (Evidence Fusion)
将来自不同来源（OCR、VLM、搜索、EXIF）的证据进行加权融合，生成置信度结论的过程

### 推理链路 (Reasoning Chain)
证据融合过程中的推理步骤记录，用于verbose模式下的调试和可视化

### 视觉语言模型 (VLM)
用于场景理解和图像分析的AI模型，支持多种提供者（OpenAI、Gemini、Zhipu）

## 模块术语

### PipelineRunner
分析流程的运行器，负责服务初始化和流程编排

### FusionService
证据融合服务，实现规则+LLM混合推理策略

### ServiceRegistry
服务注册表，管理不同VLM/OCR/搜索服务的发现和初始化

### Repository
数据访问层，负责分析记录的持久化和查询

## 技术术语

### LLMPort
LLM服务的抽象接口，用于证据融合中的中等置信度推理

### Verbose模式
详细记录推理过程的调试模式，用于生成推理链路追踪

### EvidenceItem
单个证据项，包含来源、内容、置信度和支持/反驳标志

### FusedConclusion
融合后的结论，包含陈述、概率、证据列表和类别
