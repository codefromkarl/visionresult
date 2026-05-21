# Testing Roadmap

> 测试框架迭代计划和验收标准。

---

## 现状 (2026-05-21)

| 指标 | 值 |
|------|-----|
| pytest 测试总数 | 185+ |
| Playwright E2E 测试 | 10 |
| 通过率 | 100% |
| 测试文件数 | 20+ |
| Service 覆盖 | 6/6 (100%) |
| 覆盖率阈值 | lines: 60% (目标 70%) |

### 测试分层

```
tests/
├── unit/              # 单元测试 (不依赖外部服务)
│   ├── services/      # OCR, VLM, entity, search, evidence, report
│   ├── pipeline/      # pipeline 节点函数
│   └── utils/         # 图像处理工具
├── integration/       # 集成测试 (mock 外部 API)
│   ├── test_pipeline.py      # MockPipeline 数据流
│   └── test_pipeline_e2e.py  # 端到端 pipeline
├── evaluation/        # AI 评估框架
│   ├── assertions.py  # 结构化断言
│   ├── llm_judge.py   # LLM-as-Judge
│   └── golden_examples.py  # 黄金数据集
├── quality/           # 测试质量守卫 (元测试)
│   └── test_quality_guard.py
├── e2e/               # Playwright E2E 测试
│   └── test_frontend.py
└── mocks/             # 共享 mock
    ├── fixtures.py    # 测试数据工厂
    └── mock_services.py  # Mock service 实现
```

---

## Phase 1: 基础框架 ✅

- [x] pytest + pytest-asyncio 配置
- [x] FastAPI TestClient 测试
- [x] Pydantic 模型验证测试
- [x] 图像工具函数测试
- [x] API 端点测试

---

## Phase 2: Service 层单元测试 ✅

- [x] OCR Service (PaddleOCR mock)
- [x] VLM Service (OpenAI/Gemini mock)
- [x] Entity Service (LLM mock + 降级)
- [x] Search Service (Google/Bing/Wikipedia mock)
- [x] Evidence Service (规则 + LLM 混合)
- [x] Report Service (Markdown/JSON 生成)

---

## Phase 3: 测试基础设施 ✅

- [x] Fixtures 工厂 (12 个 create_mock_* 函数)
- [x] Mock Services (6 个 Mock*Service 类)
- [x] 质量守卫 (源文件覆盖、命名规范、fixtures 完整性)
- [x] E2E 质量守卫 (行为测试检查)

---

## Phase 4: 评估框架 ✅

- [x] 结构化断言 (4 类: 结构/OCR/证据链/防幻觉)
- [x] LLM-as-Judge (3 维度: 地点/完整/证据)
- [x] 黄金数据集 (8 个场景: 涩谷/北京/室内/山景/UI/餐厅/车站/游戏)

---

## Phase 5: E2E 测试 ✅

- [x] Playwright 配置
- [x] 本地 HTTP 服务器
- [x] 文件上传流程测试
- [x] API Mock + 结果渲染测试
- [x] 错误处理测试

---

## Phase 6: 质量门禁 (当前)

### 已实现

- [x] 质量守卫自动运行
- [x] E2E 行为测试检查
- [x] 覆盖率配置 (fail_under=60)

### 待实现

- [ ] 覆盖率阈值提升至 70%
- [ ] Pre-commit hook 集成 test-qa-check.sh
- [ ] CI 中 quality guard 作为 blocking gate
- [ ] 覆盖率报告上传

---

## Phase 7: 性能测试

**触发条件**: MVP 完成后

- [ ] API 响应时间基准 (< 5s for /analyze)
- [ ] 并发请求测试 (10 concurrent uploads)
- [ ] 大文件处理测试 (10MB+ images)
- [ ] Pipeline 各阶段耗时分析

---

## Phase 8: API 契约测试

**触发条件**: API 稳定后

- [ ] OpenAPI schema 验证
- [ ] 请求/响应格式一致性
- [ ] 向后兼容性检查

---

## Phase 9: 回归测试

**触发条件**: 用户反馈 bug 后

- [ ] Bug 复现测试用例
- [ ] Golden dataset 扩展
- [ ] 自动化回归检测

---

## 验收标准

### 每次提交

| 检查项 | 标准 | 工具 |
|--------|------|------|
| Lint | 0 errors | `ruff check` |
| Format | 0 diffs | `ruff format --check` |
| Unit tests | 100% pass | `pytest tests/unit/` |
| Quality guard | 100% pass | `pytest tests/quality/` |
| E2E tests | 100% pass | `pytest tests/e2e/` |
| 覆盖率 | ≥ 60% | `pytest --cov` |

### PR 合并

| 检查项 | 标准 | 工具 |
|--------|------|------|
| 所有测试 | 100% pass | `pytest` |
| 覆盖率 | ≥ 70% | `pytest --cov --cov-fail-under=70` |
| Quality guard | 0 failures | `pytest tests/quality/` |
| E2E 行为检查 | 0 warnings | `pytest tests/quality -k E2E` |

### 发布

| 检查项 | 标准 | 工具 |
|--------|------|------|
| 所有测试 | 100% pass | CI pipeline |
| E2E 完整流程 | 通过 | Playwright |
| 健康检查 | 200 OK | `scripts/health-check.sh` |
| API 文档可访问 | 200 OK | `curl /docs` |
