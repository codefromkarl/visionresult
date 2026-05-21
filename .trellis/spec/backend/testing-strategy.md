# Testing Strategy

> 测试分层策略、Mock 路由规则、新模块测试模板。

---

## Mock 路由规则

### 何时用什么 Mock

| 测试层 | Mock 方式 | 适用场景 |
|--------|----------|---------|
| **service 层单元测试** | pytest monkeypatch / respx | 测试 service 的业务逻辑（降级、重试） |
| **pipeline 节点测试** | mock service 依赖 | 测试单个 pipeline 节点的输入输出 |
| **API 测试** | TestClient + mock service | 测试 FastAPI 路由、请求/响应格式 |
| **integration 测试** | mock VLM + 真实 pipeline | 测试完整分析流程 |

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
