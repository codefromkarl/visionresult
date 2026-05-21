# Check 快速参考

> 超精简版检查清单。用于小改动或作为 check 代理的首要依据。
> 完整规范见 spec/backend/index.md。

---

## 每次 Check 必做

### 1. 变更规模判断

| 规模 | 条件 | Check 范围 |
|------|------|-----------|
| **微小** | < 30 行，单文件 | 只跑 lint + 测试，不读 spec |
| **中等** | 新功能 / 重构 < 3 文件 | 读本文件 + 相关 layer 的 index.md |
| **大型** | 跨层改动 / > 3 文件 | 读 check.jsonl 中列出的全部 spec |

### 2. 代码规范检查（Python）

- [ ] 所有函数有类型标注（type hints）
- [ ] 使用 Pydantic v2 模式（BaseModel, Field）
- [ ] 无裸 `except`（必须指定异常类型）
- [ ] async/await 正确使用（IO 操作用 async）
- [ ] 注释使用英文，文档使用中文

### 3. 验证命令

```bash
# 按顺序执行
ruff check --fix .          # Lint
ruff format .               # Format
mypy src/                   # 类型检查
pytest                      # 测试
```

### 4. 跨层一致性

- [ ] 修改了 schema → 检查引用该 model 的所有 service 和 route
- [ ] 修改了 service 接口 → 检查所有实现类
- [ ] 新增 pipeline 节点 → 检查 graph.py 中的注册
