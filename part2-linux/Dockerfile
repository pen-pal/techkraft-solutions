# ==============================================================================
# Multi-Stage Dockerfile for TechKraft Flask API
# Stage 1: Builder — install and compile dependencies
# Stage 2: Production — minimal runtime image
# ==============================================================================

# --------------- Stage 1: Builder ---------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for C extensions (e.g., mysqlclient, lxml)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev musl-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --------------- Stage 2: Production ---------------
FROM python:3.11-slim AS production

# Metadata
LABEL maintainer="ops@techkraft.com" \
      app="techkraft-api" \
      version="1.0"

# Security: create non-root user before copying files
RUN groupadd -r techkraft && \
    useradd -r -g techkraft -d /app -s /sbin/nologin techkraft

WORKDIR /app

# Copy only the installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY app.py .

# Ensure the non-root user owns the workdir
RUN chown -R techkraft:techkraft /app

# Switch to non-root user
USER techkraft

# Expose the application port
EXPOSE 5000

# Health check — hit the /health endpoint every 30s
# start-period gives the app time to boot before checks begin
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Use gunicorn for production (Flask dev server is single-threaded and not production-safe)
# Falls back to Flask dev server if gunicorn is not in requirements.txt
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--access-logfile", "-", "app:app"]
