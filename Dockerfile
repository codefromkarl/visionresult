FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
RUN pip install -e ".[dev]" --no-cache-dir || pip install fastapi uvicorn httpx pillow pydantic pydantic-settings python-dotenv python-multipart --no-cache-dir

# Copy application code
COPY src/ src/
COPY frontend/ frontend/

# Create data directories
RUN mkdir -p data/uploads data/cache

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run the application
CMD ["uvicorn", "vision_insight.main:app", "--host", "0.0.0.0", "--port", "8001"]
