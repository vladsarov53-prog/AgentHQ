FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY config.yaml .
COPY src/ src/

# Persistent data on Railway volume
ENV DATA_DIR=/data
RUN mkdir -p /data/logs

CMD ["python", "-m", "src.main"]
