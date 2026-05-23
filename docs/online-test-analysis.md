# 线上测试问题分析与修复报告

## 问题分析

### 1. 429 错误原因

**问题**：Gemini API 返回 429 Too Many Requests

**原因分析**：
- 每次分析会调用 Gemini API **2 次**：
  1. VLM 分析（场景理解）
  2. 实体抽取（实体识别）
- 用户分析 3 次图片 = 6 次 API 调用
- Gemini API 免费版限制：**每分钟 15 次请求**（gemini-2.0-flash）
- 如果连续快速调用，会触发频率限制

**调用链路**：
```
图片上传 → OCR → VLM 分析 (1次 API) → 实体抽取 (1次 API) → 证据融合 → 报告生成
```

### 2. OCR 问题

**问题**：PaddleOCR 与 Python 3.13 不兼容

**修复**：使用 Tesseract OCR 替代

## 已完成的修复

### 1. OCR 服务 ✅

- 创建 `TesseractOCRService` 类
- 支持中文、英文、日文、韩文
- 修改 `runner.py` 使用 Tesseract

### 2. LLM Adapter ✅

- 添加 `infer_with_reasoning` 方法
- 修复推理链路记录

## 测试结果

| 功能 | 状态 | 说明 |
|------|------|------|
| API 服务 | ✅ | 正常运行 |
| 健康检查 | ✅ | 正常 |
| 图片上传 | ✅ | 正常 |
| OCR 识别 | ✅ | Tesseract 正常工作 |
| VLM 分析 | ❌ | Gemini API 429 限制 |
| 实体抽取 | ❌ | Gemini API 429 限制 |
| 证据融合 | ✅ | 正常（使用默认值） |
| 报告生成 | ✅ | 正常 |
| Pipeline Trace | ✅ | 正常记录 |

## 解决 429 问题的方案

### 方案 1：等待 1 分钟后重试

```bash
# 等待 1 分钟后再次测试
sleep 60 && curl -X POST http://localhost:8001/api/v1/analyze?verbose=true \
  -F "file=@test.png"
```

### 方案 2：使用其他 VLM 服务

```python
# 使用 OpenAI GPT-4V
VIA_VLM_PROVIDER=openai
VIA_OPENAI_API_KEY=your_key_here
```

### 方案 3：部署本地 VLM 模型

```bash
# 使用 Qwen2-VL 本地部署
VIA_VLM_PROVIDER=qwen2-vl
VIA_QWEN_MODEL_PATH=/path/to/model
```

## 建议

1. **短期**：等待 1 分钟后重试，或使用 OpenAI API
2. **中期**：升级到 Gemini API 付费版（每分钟 1000 次请求）
3. **长期**：部署本地 VLM 模型

## 测试命令

```bash
# 1. 健康检查
curl http://localhost:8001/health

# 2. 系统统计
curl http://localhost:8001/api/v1/stats

# 3. 上传图片（等待 1 分钟后）
sleep 60 && curl -X POST http://localhost:8001/api/v1/analyze?verbose=true \
  -F "file=@test.png"

# 4. 获取报告（包含推理链路）
curl http://localhost:8001/api/v1/report/{task_id}?include_trace=true
```

## 总结

- ✅ OCR 问题已修复（使用 Tesseract）
- ✅ LLM Adapter 问题已修复
- ❌ Gemini API 429 限制需要等待或更换服务
- ✅ Pipeline Trace 功能正常工作
