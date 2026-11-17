FROM python:3.12-slim

LABEL maintainer="SSA OpenLens Team"
LABEL description="SSA Disability Claims OpenLens MCP Server"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY pyproject.toml ./
COPY src/ ./src/
COPY main.py ./

# Install the package
RUN pip install --no-cache-dir -e .

# MCP servers communicate over stdio — no port exposure needed
ENV PYTHONUNBUFFERED=1
ENV OPENLENS_LOG_LEVEL=INFO

ENTRYPOINT ["python", "main.py"]
