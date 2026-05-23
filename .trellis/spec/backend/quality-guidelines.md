# Quality Guidelines

> 代码质量标准和禁止模式。

---

## 禁止模式 ❌

### 测试相关

| 禁止 | 原因 | 正确做法 |
|------|------|---------|
| E2E 只检查 DOM 结构 | 功能不能用也会通过 | 模拟用户操作 + 验证行为 |
| 测试只用 `assert result is not None` | 不验证业务正确性 | 断言具体值和业务逻辑 |
| 测试不覆盖错误路径 | 降级逻辑未验证 | 每个 try-catch 都有对应测试 |
| 测试中调用真实 AI API | 成本高、不稳定 | Mock 所有外部调用 |
| 测试文件不以 `test_` 开头 | pytest 无法发现 | 遵循命名规范 |

### 代码相关

| 禁止 | 原因 | 正确做法 |
|------|------|---------|
| 裸 `except:` | 吞掉所有异常 | 指定异常类型 `except ValueError:` |
| 无类型标注的函数 | 类型不安全 | 所有函数有 type hints |
| service 层直接 fetch 不包装 | 错误未处理 | 用 httpx + try-catch |
| 硬编码 API key | 安全风险 | 从环境变量读取 |

---

## 必须模式 ✅

### 测试相关

| 必须 | 原因 |
|------|------|
| E2E 测试模拟用户行为 | 验证功能可用 |
| 每个测试至少一个业务断言 | 验证结果正确 |
| 错误路径有独立测试 | 验证降级逻辑 |
| Mock 外部 API | 稳定性、可重复性 |
| 使用 fixtures 工厂 | 集中管理测试数据 |

### 代码相关

| 必须 | 原因 |
|------|------|
| 新 API 调用有 fallback | 服务降级 |
| Pydantic 模型有 Field 描述 | 文档化 |
| async 函数用 await | 避免协程未执行 |
| 日志记录关键操作 | 可观测性 |

---

## 断言质量标准

### 禁止的弱断言

```python
# ❌ 弱断言 — 不验证业务
assert result is not None
assert result == []
assert len(result) > 0
assert "error" not in str(result)
```

### 必须的强断言

```python
# ✅ 强断言 — 验证业务逻辑
assert result.location == "东京涩谷"
assert result.confidence >= 0.7
assert len(result.ocr_results) == 3
assert result.ocr_results[0].text == "Shibuya"
assert "涩谷" in result.report_markdown
```

---

## 降级测试模式

```python
@pytest.mark.asyncio
async def test_vlm_failure_graceful_degradation():
    """VLM 失败时应优雅降级。"""
    # 1. 验证降级前确实尝试了调用
    mock_vlm = MockVLMService()
    mock_vlm.analyze = AsyncMock(side_effect=RuntimeError("API timeout"))

    # 2. 执行降级逻辑
    result = await pipeline.execute(image_bytes, vlm=mock_vlm)

    # 3. 验证降级后数据格式正确
    assert result.status == AnalysisStatus.COMPLETED
    assert result.scene_analysis is not None
    assert result.scene_analysis.scene_type == "unknown"  # 降级标记
    assert "失败" in result.scene_analysis.description  # 降级说明
```

---

## 验收清单

### 代码提交前

- [ ] `ruff check .` 通过
- [ ] `ruff format --check .` 通过
- [ ] `pytest tests/quality/` 通过（质量守卫）
- [ ] 新增代码有对应测试
- [ ] E2E 测试验证了用户行为（不只是结构）

### PR 合并前

- [ ] 所有测试通过
- [ ] 覆盖率 ≥ 阈值（见 pyproject.toml）
- [ ] 质量守卫无新增失败
- [ ] E2E 测试覆盖新功能

---

## 国际化 (i18n) 模式

### 后端 VLM 服务

```python
# ✅ VLM 服务接受 lang 参数
async def analyze(
    self,
    image_bytes: bytes,
    ocr_results: list[OCRResult] | None = None,
    lang: str = "zh",  # 默认中文
) -> SceneAnalysis:
    ocr_context = ""
    if ocr_results:
        texts = [r.text for r in ocr_results]
        if lang == "en":
            ocr_context = f"\nOCR detected these texts: {texts}\n"
        else:
            ocr_context = f"\n图片中检测到的文字：{texts}\n"

    prompt_tpl = SCENE_ANALYSIS_PROMPT_EN if lang == "en" else SCENE_ANALYSIS_PROMPT_ZH
    prompt = prompt_tpl.format(ocr_context=ocr_context)
```

### 后端报告服务

```python
# ✅ 报告服务使用标签映射
_LABELS = {
    "zh": {"report_title": "图片分析报告", "scene": "场景", ...},
    "en": {"report_title": "Image Analysis Report", "scene": "Scene", ...},
}

def _lbl(self, key: str, lang: str = "zh") -> str:
    return self._LABELS.get(lang, self._LABELS["zh"]).get(key, key)

async def generate_user_report(self, report, lang: str = "zh") -> str:
    labels = self._LABELS.get(lang, self._LABELS["zh"])
    sections = [f"# {labels['report_title']}\n"]
```

### 前端 i18n

```javascript
// ✅ i18n.js 模块
const I18N = {
    zh: { title: '图片分析报告', ... },
    en: { title: 'Image Analysis Report', ... },
};

let currentLang = localStorage.getItem('lang') || 'zh';
export function t(key) { return I18N[currentLang]?.[key] ?? I18N.zh[key] ?? key; }
export function setLang(lang) { currentLang = lang; localStorage.setItem('lang', lang); applyI18n(); }

// ✅ HTML 使用 data-i18n 属性
// <h2 data-i18n="reportTitle">📊 分析报告</h2>

// ✅ JavaScript 使用 t() 函数
let md = `# ${t('rptTitle')}\n\n`;
```

### API 参数传递

```python
# ✅ API 端点接受 lang 参数
@router.post("/analyze")
async def create_analysis(
    file: UploadFile = File(...),
    lang: str = "zh",  # 查询参数
    ...
):
    background_tasks.add_task(_run_analysis, task_id, image_bytes, file.filename, verbose, lang)

# ✅ Pipeline 状态传递 lang
state = PipelineState(
    ...,
    lang=lang,
)
```
