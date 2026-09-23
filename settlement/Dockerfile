# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Matrix Settlement Layer Image (matrix-compute-settlement)
# ------------------------------------------------------------------------------

# --- Stage 1: Build & Dependency Wheel Compilation ---
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install shared contracts library
COPY matrix-contracts /build/matrix-contracts
RUN pip install --no-cache-dir --prefix=/install /build/matrix-contracts

# Install settlement layer package once source files are added
COPY matrix-compute-settlement /build/matrix-compute-settlement
RUN if [ -f /build/matrix-compute-settlement/pyproject.toml ] || [ -f /build/matrix-compute-settlement/setup.py ]; then \
        pip install --no-cache-dir --prefix=/install /build/matrix-compute-settlement; \
    else \
        echo "matrix-compute-settlement package files pending implementation"; \
    fi

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create dedicated non-root user
RUN groupadd -g 1000 settlegroup && \
    useradd -u 1000 -g settlegroup -s /bin/bash -m settleuser

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

USER settleuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose default settlement HTTP API port
EXPOSE 8080

# Entrypoint starting settlement REST API server
CMD ["uvicorn", "matrix_settlement.server:app", "--host", "0.0.0.0", "--port", "8080"]
