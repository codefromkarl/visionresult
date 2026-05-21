# Testing Strategy

> 测试分层策略、Mock 路由规则、新模块测试模板。

---

## 核心原则

> **结构检查 ≠ 功能测试**
> 
> 测试必须验证**用户行为**，不只是**元素存在**。
> 如果测试只检查 DOM 结构，功能完全不能用也会通过。

---

## Mock 路由规则

### 何时用什么 Mock

| 测试层 | Mock 方式 | 适用场景 |
|--------|----------|---------|
| **service 层单元测试** | pytest monkeypatch / respx | 测试 service 的业务逻辑（降级、重试） |
| **pipeline 节点测试** | mock service 依赖 | 测试单个 pipeline 节点的输入输出 |
| **API 测试** | TestClient + mock service | 测试 FastAPI 路由、请求/响应格式 |
| **integration 测试** | mock VLM + 真实 pipeline | 测试完整分析流程 |
| **E2E 测试** | Playwright + mock API | **浏览器端测试用户行为** |

### 决策树

```
测试需要调用外部 API 吗？
├─ 否 → 纯函数测试，无需 mock
└─ 是 → 
    测试的是 service 层逻辑吗？
    ├─ 是 → mock HTTP client (respx)
    └─ 否 → 
        测试的是 pipeline 编排吗？
        ├─ 是 → mock 各 service + 验证数据流
        └─ 否 → TestClient + mock service
```

---

## 分层标准

### Unit（单元测试）

**位置**: `tests/unit/`
**原则**: 单模块 + mock，不依赖真实 AI 模型

- `unit/services/` — service 层逻辑（OCR、VLM、搜索）
- `unit/pipeline/` — pipeline 节点函数
- `unit/utils/` — 工具函数（图像处理、格式化）
- `unit/models/` — Pydantic 模型验证

### Integration（集成测试）

**位置**: `tests/integration/`
**原则**: 跨模块调用链，mock 外部 API

- API 端点完整流程
- Pipeline 端到端（mock VLM/OCR）
- 数据库操作

### E2E（端到端测试）

**位置**: `tests/e2e/`
**原则**: **模拟真实用户行为，不只是检查 DOM 结构**

**必须满足的条件：**
1. ✅ 使用 `set_input_files()` / `click()` / `fill()` 模拟用户操作
2. ✅ Mock API 响应，验证请求被发送
3. ✅ 验证操作后的**状态变化**（预览显示、结果渲染、错误提示）
4. ❌ 禁止只检查元素存在 (`to_be_attached` / `to_be_visible`)

**E2E 测试模板：**

```python
class TestFeatureFlow:
    """功能流程测试 — 必须模拟用户行为。"""

    def test_user_action_triggers_expected_behavior(self, page, test_data):
        """用户操作应触发预期行为。"""
        page.goto(local_server)

        # 1. Mock API（如果需要）
        requests = []
        page.route("**/api/endpoint", lambda route: (
            requests.append(route.request),
            route.fulfill(status=200, body='{"result":"ok"}'),
        ))

        # 2. 模拟用户操作
        element = page.locator("#target")
        element.click()  # 或 set_input_files / fill / select_option

        # 3. 验证行为（不只是结构）
        assert len(requests) == 1  # API 被调用
        expect(page.locator("#result")).to_contain_class("show")  # 状态变化
        expect(page.locator("#result")).to_contain_text("预期内容")  # 内容正确
```

---

## 新模块测试 Checklist

### 新 Service

- [ ] `tests/unit/services/test_<name>.py` 创建
- [ ] 使用 monkeypatch 或 respx mock 外部调用
- [ ] 测试正常路径 + 降级路径 + 错误路径
- [ ] 测试边界情况（空输入、超大文件、无效格式）

### 新 Pipeline 节点

- [ ] `tests/unit/pipeline/test_<name>_node.py` 创建
- [ ] mock 上游节点输出
- [ ] 验证输出数据结构符合 schema
- [ ] 测试异常处理

### 新 API 端点

- [ ] `tests/test_api.py` 添加测试用例
- [ ] 使用 FastAPI TestClient
- [ ] 测试请求验证、错误响应、边界情况

### 新前端功能（关键）

- [ ] `tests/e2e/test_<feature>.py` 创建
- [ ] **必须模拟用户操作**（click / set_input_files / fill）
- [ ] **必须验证行为**（状态变化 / API 调用 / 内容渲染）
- [ ] **禁止只检查 DOM 结构**
- [ ] Mock API 响应，验证请求/响应流程
- [ ] 测试成功路径 + 失败路径

---

## E2E 测试质量守卫

### 自动检查规则

在 `tests/quality/test_quality_guard.py` 中添加：

```python
class TestE2EQuality:
    """E2E 测试质量检查 — 防止空壳测试。"""

    def test_e2e_tests_have_behavior_assertions(self):
        """E2E 测试必须有行为断言，不能只检查结构。"""
        e2e_files = list(Path("tests/e2e").glob("test_*.py"))
        for f in e2e_files:
            content = f.read_text()
            # 必须有用户操作模拟
            has_action = any(kw in content for kw in [
                "set_input_files", "click()", "fill(", "select_option",
                "dispatch_event", "type("
            ])
            # 必须有行为断言
            has_behavior = any(kw in content for kw in [
                "to_contain_class", "to_contain_text", "assert.*requests",
                "wait_for_request", "wait_for_selector"
            ])
            # 禁止只有结构检查
            only_structure = all(kw in content for kw in [
                "to_be_attached", "to_be_visible"
            ]) and not has_action

            assert has_action, f"{f.name}: 缺少用户操作模拟 (set_input_files/click/fill)"
            assert has_behavior, f"{f.name}: 缺少行为断言 (状态变化/API调用)"
            assert not only_structure, f"{f.name}: 只有结构检查，没有功能测试"
```

---

## Agent 驱动的测试评估

### 对比：机械检查 vs Agent 评估

| 维度 | 机械检查 | Agent 评估 |
|------|---------|------------|
| 检查方式 | 关键字匹配 | 语义理解 |
| 能否理解需求 | ❌ 不能 | ✅ 能 |
| 能否评估测试质量 | ❌ 只能检查存在 | ✅ 能评估覆盖度 |
| 能否生成建议 | ❌ 不能 | ✅ 能生成测试代码 |
| 能否发现缺口 | ❌ 只能检查已知模式 | ✅ 能发现未知缺口 |

### Agent 评估维度

```
需求覆盖度 (0-25分): 测试是否覆盖了所有需求点？
行为验证度 (0-25分): 测试是否验证了真实用户行为？
边界覆盖度 (0-25分): 测试是否覆盖了错误路径、边界条件？
可维护性   (0-25分): 测试是否清晰、可重复、易维护？
```

### 使用方式

```bash
# 评估单个测试文件
python scripts/eval-tests.py tests/e2e/test_frontend.py

# 列出所有测试
python scripts/eval-tests.py --all
```

### Agent 评估流程

```
读取 PRD → 提取需求点
    ↓
读取实现代码 → 理解功能逻辑
    ↓
读取测试代码 → 理解测试覆盖
    ↓
语义分析 → 评估需求-测试对齐度
    ↓
生成报告 → 评分 + 缺口 + 建议
```

### 评估输出示例

```
📊 测试质量评分: 75/100

✅ 优点:
  - 覆盖了上传功能的完整流程
  - Mock 了 API 响应

❌ 缺点:
  - 缺少错误路径测试
  - 缺少边界条件测试

⚠️ 覆盖缺口 (2 个):
  🔴 [high] 缺少上传失败测试
    需求: 错误处理
    建议: def test_upload_error(): ...

💡 改进建议:
  - 添加大文件上传测试
  - 添加网络超时测试
```

---

## 测试失败时的排查顺序

```
测试失败
├── 是 E2E 测试吗？
│   ├── 是 → 检查是否有真实用户操作，不是只检查 DOM
│   └── 否 → 继续
├── 是集成测试吗？
│   ├── 是 → 检查 mock 是否正确设置
│   └── 否 → 继续
└── 是单元测试吗？
    └── 检查输入/输出是否符合预期
```
