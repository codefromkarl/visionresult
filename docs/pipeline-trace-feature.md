# 思考链条与调用证据链功能实现总结

## 实现概述

本次实现了完整的思考链条和调用证据链功能，包括：

1. **扩展数据模型** — 添加 PipelineStep、ReasoningTrace 等模型
2. **修改 LLM 提示词** — 支持返回详细推理过程
3. **添加 verbose 模式** — API 参数控制是否记录中间步骤
4. **前端可视化** — 展示 pipeline 调用链路图和思考链条

## 修改的文件

### 1. 数据模型 (`src/vision_insight/models/schemas.py`)

新增模型：
- `ReasoningStep` — 单个推理步骤
- `ReasoningTrace` — 完整推理链路
- `PipelineStep` — Pipeline 阶段执行详情
- `PipelineTrace` — 完整 Pipeline 执行追踪

修改：
- `AnalysisReport` 添加 `pipeline_trace` 字段

### 2. Pipeline 图 (`src/vision_insight/pipeline/graph.py`)

新增功能：
- `PipelineState` 添加 `verbose` 和 `pipeline_trace` 字段
- `_start_pipeline_step()` — 记录阶段开始
- `_end_pipeline_step()` — 记录阶段结束
- 所有节点函数添加详细的输入/输出记录

### 3. Pipeline Runner (`src/vision_insight/pipeline/runner.py`)

修改：
- `execute()` 方法添加 `verbose` 参数
- 动态设置 FusionService 的 verbose 模式
- 收集推理链路并添加到 PipelineTrace

### 4. 证据融合服务 (`src/vision_insight/services/evidence/fusion_service.py`)

新增功能：
- `LLMPort.infer_with_reasoning()` — 返回推理过程
- `FusionService.set_verbose()` — 动态启用/禁用详细模式
- `FusionService.get_reasoning_traces()` — 获取收集的推理链路
- `_synthesize_conclusion()` — 记录详细的推理步骤

修改：
- `_build_llm_prompt()` — 支持 verbose 模式下的提示词

### 5. API 路由 (`src/vision_insight/api/routes.py`)

新增功能：
- `POST /api/v1/analyze?verbose=true` — 启用 verbose 模式
- `GET /api/v1/report/{id}?include_trace=true` — 获取包含推理链路的报告

修改：
- `_run_analysis()` — 支持 verbose 参数
- `_report_to_record()` — 保存 pipeline_trace_json

### 6. 数据库 (`src/vision_insight/core/database.py`)

修改：
- `AnalysisRecord` 添加 `pipeline_trace_json` 字段

### 7. 前端 (`frontend/index.html`)

新增功能：
- Verbose 模式复选框
- 推理链路可视化按钮
- Pipeline 时间线组件
- 推理卡片组件
- 完整的 CSS 样式

### 8. 测试 (`tests/test_pipeline_trace.py`)

新增测试：
- 数据模型测试
- FusionService verbose 模式测试
- 推理链路收集测试

## 使用示例

### API 调用

```bash
# 1. 启用 verbose 模式分析图片
curl -X POST http://localhost:8000/api/v1/analyze?verbose=true \
  -F "file=@test.jpg"

# 2. 获取任务 ID 后，查询包含推理链路的报告
curl http://localhost:8000/api/v1/report/{task_id}?include_trace=true
```

### 前端使用

1. 打开前端页面
2. 上传图片
3. 勾选「启用详细推理链路」复选框
4. 点击「开始分析」
5. 分析完成后，点击「🔍 推理链路」按钮查看详细推理过程

## 返回数据结构

### Pipeline Trace

```json
{
  "pipeline_trace": {
    "steps": [
      {
        "stage_name": "preprocess",
        "status": "success",
        "start_time": "2024-01-01T00:00:00",
        "end_time": "2024-01-01T00:00:00.050",
        "duration_ms": 50,
        "input_summary": "Image size: 1024000 bytes",
        "output_summary": "1920x1080, 1000.0KB",
        "key_findings": [
          "Format: JPEG",
          "GPS: No",
          "Capture time: Not available"
        ],
        "input_data": {"image_size_bytes": 1024000},
        "output_data": {
          "width": 1920,
          "height": 1080,
          "format": "JPEG",
          "has_gps": false,
          "has_capture_time": false
        }
      }
    ],
    "reasoning_traces": [
      {
        "conclusion_category": "location",
        "conclusion_statement": "拍摄地点: 东京涩谷",
        "final_probability": 0.85,
        "steps": [
          {
            "step_id": 1,
            "action": "rule_match",
            "description": "High confidence match (>0.8)",
            "input_summary": "3 evidence items, max confidence=0.95",
            "output_summary": "Best match: [ocr] OCR detected 'Shibuya'...",
            "confidence_before": 0.95,
            "confidence_after": 0.85,
            "duration_ms": 5,
            "metadata": {
              "best_source": "ocr",
              "num_supporting": 2
            }
          }
        ],
        "strategy_used": "rule",
        "total_duration_ms": 5
      }
    ],
    "total_duration_ms": 500,
    "verbose_mode": true
  }
}
```

## 设计决策

### 1. Verbose 模式默认关闭

为了避免影响性能，verbose 模式默认关闭，需要显式启用。

### 2. 推理链路按结论分类

每个结论（地点、场景、时间等）都有独立的推理链路，便于理解每个推断的过程。

### 3. 三种推理策略

- **rule** — 高置信度直接规则匹配
- **llm** — 中置信度使用 LLM 辅助推理
- **uncertain** — 低置信度标记为不确定

### 4. 前端可视化

使用时间线和卡片式设计，直观展示：
- Pipeline 各阶段的执行顺序和耗时
- 每个结论的推理策略和证据链
- 关键发现和错误信息

## 测试验证

所有新增功能都有对应的测试：

```bash
# 运行 pipeline trace 测试
.venv/bin/python -m pytest tests/test_pipeline_trace.py -v

# 运行 evidence 服务测试
.venv/bin/python -m pytest tests/unit/services/test_evidence.py -v
```

## 总结

本次实现完整地支持了思考链条和调用证据链的展示功能，包括：

✅ 扩展数据模型 — 支持 PipelineTrace、ReasoningTrace 等
✅ 修改 LLM 提示词 — 支持返回详细推理过程
✅ 添加 verbose 模式 — API 参数控制
✅ 前端可视化 — 完整的时间线和推理卡片组件
✅ 测试覆盖 — 所有新功能都有测试验证
✅ 文档更新 — README.md 包含使用说明

用户现在可以通过 verbose 模式查看完整的推理过程，包括：
- 每个 Pipeline 阶段的输入/输出和耗时
- 每个结论的推理策略（规则匹配/LLM推理）
- 证据的置信度变化
- 关键发现和错误信息
