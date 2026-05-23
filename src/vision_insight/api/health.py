"""Enhanced health check endpoints for monitoring."""

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from vision_insight import __version__
from vision_insight.core.config import settings
from vision_insight.core.database import get_database_stats, get_engine

router = APIRouter(tags=["system"])

# Track application start time
_app_start_time = time.time()


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    timestamp: str
    checks: dict[str, Any]


class ComponentHealth(BaseModel):
    """Individual component health status."""

    status: str  # "ok", "error", "degraded"
    message: str = ""
    latency_ms: float = 0


def _check_database() -> ComponentHealth:
    """Check database connectivity and status."""
    start = time.time()
    try:
        engine = get_engine()
        # Try to execute a simple query
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # Get stats
        stats = get_database_stats()
        latency = (time.time() - start) * 1000

        return ComponentHealth(
            status="ok",
            message=f"Connected. {stats['total']} records total.",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.time() - start) * 1000
        return ComponentHealth(
            status="error",
            message=f"Database error: {str(e)[:100]}",
            latency_ms=round(latency, 2),
        )


def _check_vlm_service() -> ComponentHealth:
    """Check VLM service configuration."""
    provider = settings.vlm_provider

    if provider == "openai" and settings.openai_api_key:
        return ComponentHealth(status="ok", message="OpenAI API key configured")
    elif provider == "gemini" and settings.gemini_api_key:
        return ComponentHealth(status="ok", message="Gemini API key configured")
    elif provider == "zhipu" and settings.zhipu_api_key:
        return ComponentHealth(status="ok", message="Zhipu API key configured")
    else:
        return ComponentHealth(
            status="error",
            message=f"No API key configured for provider: {provider}",
        )


def _check_search_service() -> ComponentHealth:
    """Check search service configuration."""
    has_google = bool(settings.google_api_key and settings.google_cse_id)
    has_bing = bool(settings.bing_api_key)

    if has_google or has_bing:
        services = []
        if has_google:
            services.append("Google")
        if has_bing:
            services.append("Bing")
        return ComponentHealth(
            status="ok",
            message=f"Search services configured: {', '.join(services)}",
        )
    else:
        return ComponentHealth(
            status="degraded",
            message="No search API keys configured. Will use Wikipedia only.",
        )


@router.get("/health", summary="Basic health check")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "version": __version__}


@router.get("/health/detailed", summary="Detailed health check", response_model=HealthStatus)
async def detailed_health_check():
    """Detailed health check with component status."""
    # Check each component
    db_health = _check_database()
    vlm_health = _check_vlm_service()
    search_health = _check_search_service()

    # Determine overall status
    component_statuses = [db_health.status, vlm_health.status, search_health.status]

    if "error" in component_statuses:
        overall_status = "unhealthy"
    elif "degraded" in component_statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    # Calculate uptime
    uptime = time.time() - _app_start_time

    return HealthStatus(
        status=overall_status,
        version=__version__,
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.now(UTC).isoformat(),
        checks={
            "database": db_health.model_dump(),
            "vlm_service": vlm_health.model_dump(),
            "search_service": search_health.model_dump(),
            "upload_dir": {
                "status": "ok" if settings.upload_dir.exists() else "error",
                "message": str(settings.upload_dir),
            },
            "cache_dir": {
                "status": "ok" if settings.cache_dir.exists() else "error",
                "message": str(settings.cache_dir),
            },
        },
    )


@router.get("/health/ready", summary="Readiness check")
async def readiness_check():
    """Kubernetes readiness probe endpoint."""
    db_health = _check_database()

    if db_health.status == "error":
        raise HTTPException(status_code=503, detail="Database not ready")

    return {"status": "ready"}


@router.get("/health/live", summary="Liveness check")
async def liveness_check():
    """Kubernetes liveness probe endpoint."""
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}
