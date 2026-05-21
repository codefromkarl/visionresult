# Testing Roadmap

> 测试框架迭代计划。按优先级排列，随项目开发逐步推进。

---

## Phase 1: 基础测试框架（当前）

- [ ] pytest + pytest-asyncio 配置
- [ ] FastAPI TestClient 基础测试
- [ ] Pydantic 模型验证测试
- [ ] 图像工具函数测试
- [ ] 基础 API 端点测试（health, analyze, report）

---

## Phase 2: Service 层单元测试

- [ ] OCR Service mock 测试
- [ ] VLM Service mock 测试
- [ ] Entity Service 测试
- [ ] Search Service 测试（mock HTTP）
- [ ] Evidence Service 测试
- [ ] Report Service 测试

---

## Phase 3: Pipeline 集成测试

- [ ] Pipeline 节点串联测试（mock 所有 service）
- [ ] 端到端分析流程测试（mock VLM/OCR）
- [ ] 错误传播和降级测试
- [ ] 超时和重试测试

---

## Phase 4: API 端到端测试

- [ ] 图片上传完整流程
- [ ] URL 分析完整流程
- [ ] 并发请求测试
- [ ] 大文件处理测试

---

## Phase 5: AI 质量评估

- [ ] LLM-as-Judge 评估框架
- [ ] Golden dataset 建立（10-20 张标注图片）
- [ ] 评估维度：场景准确率、OCR 准确率、地点推测准确率
- [ ] 集成到 CI（手动触发）
