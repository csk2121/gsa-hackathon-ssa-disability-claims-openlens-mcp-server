FROM python:3.12-slim

LABEL maintainer="SSA OpenLens Team"
LABEL description="SSA Disability Claims OpenLens MCP Server"

# MCP servers communicate over stdio — no port exposure needed
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OPENLENS_LOG_LEVEL=INFO

WORKDIR /app

# Runtime dependencies only (deploy/requirements.txt has no test or lint tools).
# No system packages are installed: the server needs nothing beyond Python.
COPY deploy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# main.py imports the server from ./src, so the package itself is not installed.
COPY src/ ./src/
COPY main.py ./

# Run as an unprivileged user that cannot modify the application files.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin openlens
USER openlens

ENTRYPOINT ["python", "main.py"]
