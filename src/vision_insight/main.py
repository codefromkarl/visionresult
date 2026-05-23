"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from vision_insight import __version__
from vision_insight.api.health import router as health_router
from vision_insight.api.routes import router
from vision_insight.core.auth import setup_api_key_auth
from vision_insight.core.config import settings
from vision_insight.core.rate_limiter import setup_rate_limiting
from vision_insight.core.request_id import setup_request_id

app = FastAPI(
    title="Visual Insight Agent",
    description="""## 多模态图片分析系统

### 核心能力
- 📸 **图片分析**: 上传图片，自动识别场景、地点、时间、人物
- 🔍 **OCR识别**: 提取图片中的文字（中/日/英/韩）
- 🌐 **联网验证**: 搜索验证识别结果
- 📊 **证据链推理**: 多源证据融合，置信度评估

### 快速开始
1. `POST /api/v1/analyze` 上传图片
2. `GET /api/v1/analyze/{id}/stream` 实时进度
3. `GET /api/v1/report/{id}` 获取报告

### API 文档
- Swagger UI: `/docs`
- ReDoc: `/redoc`
""",
    version=__version__,
    tags_metadata=[
        {
            "name": "analysis",
            "description": "图片分析相关接口",
        },
        {
            "name": "reports",
            "description": "报告查询与管理",
        },
        {
            "name": "knowledge",
            "description": "知识库查询与问答",
        },
        {
            "name": "system",
            "description": "系统状态",
        },
    ],
)

# Setup request ID tracking
setup_request_id(app)

# Setup rate limiting
setup_rate_limiting(
    app,
    requests_per_minute=settings.rate_limit_per_minute,
    requests_per_hour=settings.rate_limit_per_hour,
)

# Setup API key authentication (if enabled)
setup_api_key_auth(app, enabled=settings.enable_api_key_auth)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    max_age=600,  # 预检请求缓存 10 分钟
)

app.include_router(router, prefix="/api/v1")
app.include_router(health_router)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML page."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Frontend not found. Visit /docs for API documentation."}
