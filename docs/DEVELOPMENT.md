# 开发指南

## 开发环境设置

### 前置要求

- Python 3.11+
- uv (推荐) 或 pip
- Docker (可选，用于生产部署)

### 快速开始

```bash
# 克隆仓库
git clone https://github.com/your-org/visionresult.git
cd visionresult

# 安装依赖（使用 uv）
uv sync --extra dev

# 或使用 pip
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API keys

# 运行开发服务器
uvicorn vision_insight.main:app --reload --port 8000
```

## 开发命令

### 质量检查

```bash
# 运行完整质量门禁
make quality

# 分步运行
make lint      # Ruff 检查
make format    # 自动格式化
make mypy      # 类型检查
make test      # 运行测试
```

### 测试

```bash
# 运行所有测试
make test

# 运行单元测试
make test-unit

# 运行测试 + 覆盖率
make test-cov

# 运行特定测试
uv run pytest tests/unit/core/test_auth.py -v
```

### 代码格式化

```bash
# 自动格式化
make format

# 检查格式
make lint
```

## 项目结构

```
visionresult/
├── src/vision_insight/
│   ├── api/              # FastAPI 路由
│   │   ├── health.py     # 健康检查端点
│   │   └── routes.py     # API 路由
│   ├── core/             # 核心配置
│   │   ├── auth.py       # API Key 认证
│   │   ├── config.py     # 配置管理
│   │   ├── database.py   # 数据库
│   │   ├── rate_limiter.py # 速率限制
│   │   └── sanitizer.py  # 日志脱敏
│   ├── models/           # Pydantic 数据模型
│   │   └── schemas.py    # API 和 Pipeline 数据模型
│   ├── pipeline/         # 分析流程
│   │   ├── graph.py      # LangGraph 图定义
│   │   └── runner.py     # Pipeline 运行器
│   ├── services/         # 服务实现
│   │   ├── ocr/          # OCR 服务
│   │   ├── vlm/          # VLM 服务
│   │   ├── entity/       # 实体抽取
│   │   ├── search/       # 联网检索
│   │   ├── evidence/     # 证据融合
│   │   └── report/       # 报告生成
│   └── utils/            # 工具函数
├── frontend/             # 前端代码
├── tests/                # 测试代码
│   ├── unit/             # 单元测试
│   ├── integration/      # 集成测试
│   └── e2e/              # E2E 测试
├── scripts/              # 工具脚本
├── docs/                 # 文档
├── Makefile              # 开发命令
└── pyproject.toml        # 项目配置
```

## 添加新功能

### 1. 创建新服务

```python
# src/vision_insight/services/my_service.py
from __future__ import annotations

from typing import Protocol


class MyService(Protocol):
    """My service interface."""
    
    async def do_something(self, input_data: str) -> str:
        """Do something with input data."""
        ...


class MyServiceImpl:
    """My service implementation."""
    
    async def do_something(self, input_data: str) -> str:
        """Do something with input data."""
        return f"Processed: {input_data}"
```

### 2. 注册服务

```python
# src/vision_insight/core/service_registry.py
from vision_insight.services.my_service import MyService, MyServiceImpl

class ServiceRegistry:
    def __init__(self):
        # ... existing services ...
        self._my_service: MyService | None = None
    
    @property
    def my_service(self) -> MyService:
        if self._my_service is None:
            self._my_service = MyServiceImpl()
        return self._my_service
```

### 3. 添加 API 路由

```python
# src/vision_insight/api/routes.py
from vision_insight.core.service_registry import get_service_registry

@router.post("/my-endpoint")
async def my_endpoint(request: MyRequest):
    """My endpoint description."""
    registry = get_service_registry()
    result = await registry.my_service.do_something(request.input_data)
    return {"result": result}
```

### 4. 添加测试

```python
# tests/unit/services/test_my_service.py
from __future__ import annotations

import pytest
from vision_insight.services.my_service import MyServiceImpl


@pytest.fixture
def my_service():
    return MyServiceImpl()


@pytest.mark.asyncio
async def test_do_something(my_service):
    result = await my_service.do_something("test")
    assert result == "Processed: test"
```

## 添加新配置

### 1. 添加配置字段

```python
# src/vision_insight/core/config.py
class Settings(BaseSettings):
    # ... existing settings ...
    
    my_new_setting: str = "default_value"
```

### 2. 更新 .env.example

```bash
# .env.example
VIA_MY_NEW_SETTING=default_value
```

### 3. 使用配置

```python
from vision_insight.core.config import settings

def my_function():
    value = settings.my_new_setting
    # ...
```

## 调试技巧

### 使用 Verbose 模式

```bash
# 启用详细日志
export VIA_DEBUG=true
uvicorn vision_insight.main:app --reload --port 8000
```

### 查看 Pipeline Trace

```bash
# 启用 verbose 模式分析
curl -X POST http://localhost:8000/api/v1/analyze?verbose=true \
  -F "file=@test.jpg"

# 获取包含推理链路的报告
curl http://localhost:8000/api/v1/report/{task_id}?include_trace=true
```

### 使用 Python 调试器

```python
# 在代码中添加断点
import pdb; pdb.set_trace()

# 或使用 IPython
import IPython; IPython.embed()
```

## 常见问题

### Q: 测试失败怎么办？

```bash
# 运行特定测试查看详细错误
uv run pytest tests/unit/core/test_auth.py -v

# 查看完整错误输出
uv run pytest tests/unit/core/test_auth.py -v --tb=long
```

### Q: 类型检查失败怎么办？

```bash
# 查看详细类型错误
uv run mypy src/vision_insight --no-error-summary

# 忽略特定错误（临时）
def my_function() -> None:  # type: ignore[override]
    pass
```

### Q: 如何添加新的 VLM provider？

1. 创建新的服务实现 `src/vision_insight/services/vlm/new_provider.py`
2. 实现 `VLMService` 接口
3. 在 `service_registry.py` 中注册
4. 在 `config.py` 中添加配置
5. 添加单元测试

### Q: 如何添加新的 OCR 引擎？

1. 创建新的服务实现 `src/vision_insight/services/ocr/new_engine.py`
2. 实现 `OCRService` 接口
3. 在 `service_registry.py` 中注册
4. 在 `config.py` 中添加配置
5. 添加单元测试

## 最佳实践

1. **使用 Protocol 定义接口** - 便于测试和替换实现
2. **编写单元测试** - 确保代码质量
3. **使用类型注解** - 提高代码可读性
4. **遵循 PEP 8** - 保持代码风格一致
5. **编写文档字符串** - 便于他人理解代码
6. **使用 async/await** - 提高并发性能
7. **处理异常** - 优雅处理错误情况
8. **记录日志** - 便于调试和监控

## 贡献指南

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/my-feature`)
3. 提交更改 (`git commit -m 'Add my feature'`)
4. 推送到分支 (`git push origin feature/my-feature`)
5. 创建 Pull Request

## 资源链接

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [PaddleOCR 文档](https://github.com/PaddlePaddle/PaddleOCR)
