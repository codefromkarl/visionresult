FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir . || pip install fastapi uvicorn httpx pillow pydantic pydantic-settings python-dotenv python-multipart pytesseract --no-cache-dir

# Copy frontend
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
