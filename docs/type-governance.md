# 类型治理规范 (Type Governance)

## 现状

| 指标 | 数值 |
|---|---|
| mypy 错误 | 0 (from 92) |
| `type: ignore` 数量 | 0 |
| `disable_error_code` 模块 | 3 (routes, database, image) |

## 架构决策

### 为什么不全开 strict

`strict = true` 会暴露 ~130 个历史类型债（缺返回类型、`Any` 穿透），与业务迭代冲突。
采用**渐进式策略**：先从 0 错误基线开始，每次 PR 可以"顺手"补类型。

### 已知的结构性 type: ignore 来源

| 来源 | 原因 | 治理策略 |
|---|---|---|
| SQLAlchemy Column 赋值 | ORM 字段类型 `Column[T]` 与运行时 `T` 不兼容 | pyproject.toml `disable_error_code` |
| paddleocr/pytesseract | 无 stubs | `ignore_missing_imports` |
| LangGraph StateGraph | 泛型签名复杂 | `ignore_missing_imports` |
| PIL Exif | 不是标准 dict 子类 | `disable_error_code` |

## 护栏机制

### 1. pyproject.toml [tool.mypy]

- `warn_unused_ignores = true` — 防止无效 type: ignore 滋生
- `no_implicit_optional = true` — 防止 `param = None` 不写 Optional

### 2. pre-commit

`.pre-commit-config.yaml` 在每次 commit 时运行 ruff + mypy。

### 3. CI quality-gate.yml

lint job 包含 `mypy src/vision_insight`，PR 合入前必须通过。

### 4. Makefile

```bash
make quality   # lint + mypy + test（等同 CI）
make type-audit  # 统计 type: ignore 数量
```

## 渐进治理路线

### Phase 1 ✅ 已完成

- [x] 92 → 0 mypy 错误
- [x] 清除所有 `type: ignore`
- [x] pyproject.toml 配置
- [x] pre-commit + CI + Makefile

### Phase 2 — 下一迭代

- [ ] `no-any-return` 错误清零（~18 处 httpx/json Any 穿透）
- [ ] 给 routes.py 的 `_record_to_report` 引入 typed DTO layer 替代 Column 直读
- [ ] `make type-audit` 数量趋势追踪

### Phase 3 — 长期

- [ ] 考虑 SQLAlchemy 2.0 typed mapping (Mapped[T]) 替代 Column
- [ ] `warn_return_any = true` 全局开启
