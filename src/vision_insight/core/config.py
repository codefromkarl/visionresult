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
    api_keys: str = ""  # Comma-separated API keys for authentication

    # Paths
    upload_dir: Path = Path("data/uploads")
    cache_dir: Path = Path("data/cache")
    images_dir: Path = Path("data/images")

    # VLM
    vlm_provider: str = "zhipu"  # qwen2-vl | openai | gemini | zhipu
    openai_api_key: str = ""
    gemini_api_key: str = ""
    zhipu_api_key: str = ""
    qwen_model_path: str = ""

    # OCR
    ocr_provider: str = "baidu"  # baidu | tesseract | paddle
    ocr_lang: str = "ch"  # ch | en | japan | korean

    # Baidu OCR
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""
    baidu_ocr_accurate: bool = True  # Use high-accuracy mode

    # Database — unused: the project uses SQLite (see core/database.py).
    # Kept here so that VIA_DATABASE_URL in .env doesn't cause a validation error.
    database_url: str = ""

    # Search
    google_api_key: str = ""
    google_cse_id: str = ""
    bing_api_key: str = ""

    # Cloudflare
    deploy_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_zone_id: str = ""
    pages_project: str = "vision-insight"

    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Auth
    enable_api_key_auth: bool = False  # Enable API key authentication

    model_config = {"env_prefix": "VIA_", "env_file": ".env"}


settings = Settings()


def ensure_directories() -> None:
    """Ensure required directories exist.

    Call this at application startup, not at import time.
    """
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)
