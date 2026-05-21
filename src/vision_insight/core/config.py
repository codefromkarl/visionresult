"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # Paths
    upload_dir: Path = Path("data/uploads")
    cache_dir: Path = Path("data/cache")

    # VLM
    vlm_provider: str = "qwen2-vl"  # qwen2-vl | openai | gemini
    openai_api_key: str = ""
    gemini_api_key: str = ""
    qwen_model_path: str = ""

    # OCR
    ocr_lang: str = "ch"  # ch | en | japan | korean

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vision_insight"

    # Search
    google_api_key: str = ""
    google_cse_id: str = ""
    bing_api_key: str = ""

    # Cloudflare
    deploy_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_zone_id: str = ""
    pages_project: str = "vision-insight"

    model_config = {"env_prefix": "VIA_", "env_file": ".env"}


settings = Settings()

# Ensure directories exist
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
