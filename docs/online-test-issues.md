# 线上测试问题分析报告

## 问题概述

用户在线上测试时遇到请求超时问题。经过分析，发现以下问题：

## 发现的问题

### 1. PaddleOCR 初始化失败 ❌

**问题**：
- `use_gpu` 参数不被新版本支持
- `show_log` 参数不被新版本支持
- PaddlePaddle 与 Python 3.13 不兼容

**错误日志**：
```
ValueError: Unknown argument: use_gpu
ValueError: Unknown argument: show_log
NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
```

**修复状态**：已尝试修复，但由于 PaddlePaddle 版本兼容性问题，OCR 功能无法正常工作。

### 2. Gemini API 429 错误 ❌

**问题**：请求频率限制

**错误日志**：
```
Retryable HTTP 429, attempt 1/3, waiting 1.0s
Retryable HTTP 429, attempt 2/3, waiting 2.0s
VLM analysis failed: Client error '429 Too Many Requests'
```

**原因**：Gemini API 免费版有请求频率限制。

### 3. LLM Adapter 缺少方法 ❌ → ✅ 已修复

**问题**：`_VLMPortAdapter` 没有 `infer_with_reasoning` 方法

**修复**：已添加 `infer_with_reasoning` 方法

## 解决方案

### 方案 1：使用其他 OCR 引擎

```python
# 使用 Tesseract OCR
import pytesseract
from PIL import Image

def extract_text(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(image, lang='chi_sim+eng')
    return text
```

### 方案 2：使用云服务 OCR

```python
# 使用 Google Cloud Vision API
from google.cloud import vision

def extract_text(image_bytes):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)
    return response.text_annotations[0].description
```

### 方案 3：跳过 OCR 步骤

在 OCR 失败时，系统会继续执行后续步骤，只是没有 OCR 结果。

## 当前状态

| 功能 | 状态 | 说明 |
|------|------|------|
| API 服务 | ✅ | 正常运行 |
| 健康检查 | ✅ | 正常 |
| 图片上传 | ✅ | 正常 |
| OCR 识别 | ❌ | PaddleOCR 兼容性问题 |
| VLM 分析 | ❌ | Gemini API 429 限制 |
| 实体抽取 | ❌ | Gemini API 429 限制 |
| 证据融合 | ✅ | 正常（使用默认值） |
| 报告生成 | ✅ | 正常 |
| Pipeline Trace | ✅ | 正常记录 |

## 建议

1. **短期**：使用 Tesseract OCR 替代 PaddleOCR
2. **中期**：升级到 Gemini API 付费版或使用其他 VLM 服务
3. **长期**：部署本地 VLM 模型（如 Qwen2-VL）

## 测试命令

```bash
# 1. 健康检查
curl http://localhost:8001/health

# 2. 系统统计
curl http://localhost:8001/api/v1/stats

# 3. 上传图片（启用推理链路）
curl -X POST http://localhost:8001/api/v1/analyze?verbose=true \
  -F "file=@test.png"

# 4. 获取报告（包含推理链路）
curl http://localhost:8001/api/v1/report/{task_id}?include_trace=true
```

## 总结

主要问题是 **PaddleOCR 兼容性** 和 **Gemini API 频率限制**。Pipeline Trace 功能本身工作正常，但由于上游服务问题，分析结果不完整。

---

## 2026-05-22 更新：降级与验证状态

### 已完成修复

1. **OCR 降级链**
   - 新增 `CompositeOCRService`。
   - 支持按配置优先使用 Baidu / Tesseract / PaddleOCR。
   - 当某个 OCR provider 初始化失败、运行时报错或返回空结果时，会继续尝试下一个 provider。
   - 所有 OCR 都不可用时返回空 OCR 结果，pipeline 继续执行。

2. **VLM 降级链**
   - 新增 `CompositeVLMService` 和 `DegradedVLMService`。
   - `VIA_VLM_PROVIDER=auto` 时按 Zhipu → OpenAI → Gemini 选择可用 provider。
   - 当前 provider 因 429、超时或其他错误失败时，自动尝试下一个 provider。
   - 全部不可用时返回明确的 `unknown` 场景，并在报告中说明 VLM 当前不可用，避免瞎猜。

3. **实体抽取降级**
   - 新增 `RuleBasedEntityService`。
   - 无 LLM API key 时仍可从 VLM 地点猜测和高置信 OCR 文本中抽取保守实体。

4. **测试与质量守卫**
   - 新增 fallback、安全、日志、限流、request-id、sanitizer 测试。
   - 修复 E2E 测试与当前前端 DOM/交互不一致的问题。
   - 修复 pytest 收集顺序，避免 Playwright E2E 影响后续 pytest-asyncio 测试。
   - 统一健康检查 / OpenAPI 版本来源为 `vision_insight.__version__`。

### 当前状态

| 功能 | 状态 | 说明 |
|------|------|------|
| API 服务 | ✅ | 本地启动验证通过 |
| 健康检查 | ✅ | `/health` 返回 `{"status":"ok","version":"0.1.0"}` |
| 前端首页 | ✅ | `GET /` 返回 Visual Insight Agent 页面 |
| 图片上传 | ✅ | `/api/v1/analyze?verbose=true` 返回 task_id |
| OCR 识别 | ✅/降级 | Tesseract/Baidu/Paddle 可按配置 fallback；不可用时返回空 OCR |
| VLM 分析 | ✅/降级 | Provider 失败或无 key 时进入明确 degraded 模式 |
| 实体抽取 | ✅/降级 | 无 LLM key 时使用规则抽取 |
| 证据融合 | ✅ | 规则 + LLM/空 LLM 降级正常 |
| 报告生成 | ✅ | 本地 smoke test 返回 completed |
| Pipeline Trace | ✅ | `include_trace=true` 返回 pipeline_trace |

### 验证结果

```bash
uv run ruff check src tests
# All checks passed!

uv run pytest -q
# 395 passed, 1 skipped, 6 warnings
```

本地运行 smoke test：

```text
HEALTH={"status":"ok","version":"0.1.0"}
FRONT_STATUS=200 TITLE=<title>Visual Insight Agent
ANALYZE={"task_id":"...","status":"pending","message":"Analysis started..."}
REPORT_STATUS=completed
REPORT_HAS_TRACE=True
```

### 已知非阻塞项

- `uv run mypy src/vision_insight` 当前仍有历史类型问题，主要集中在 SQLAlchemy 动态字段、第三方库缺失 stubs（PaddleOCR/Tesseract）、以及旧代码的 Optional 标注。功能测试已通过，mypy 建议作为单独类型治理任务处理。
