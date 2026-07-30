# syntax=docker/dockerfile:1.7
#
# Two-stage Alpine build. requests / pyyaml / python-dateutil all publish
# musllinux wheels (pyyaml's libyaml extension included), so nothing compiles
# and the runtime layer carries no Debian CVE backlog.

# ---- Stage 1: build the virtualenv ----
FROM python:3.13-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apk add --no-cache build-base libffi-dev openssl-dev yaml-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.13-alpine

# Set Python path
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apk add --no-cache libffi openssl yaml

# Set working directory
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY src/ ./src/

# Create data directory for database, then drop to a non-root user.
RUN addgroup -g 1000 -S appuser \
    && adduser -u 1000 -S -G appuser -H -s /sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER 1000:1000

# Run the application
CMD ["python", "src/main.py"]
