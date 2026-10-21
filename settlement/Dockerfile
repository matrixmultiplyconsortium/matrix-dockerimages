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

# Install shared contracts library and settlement layer package together
COPY matrix-contracts /build/matrix-contracts
COPY matrix-compute-settlement /build/matrix-compute-settlement
RUN pip install --no-cache-dir --prefix=/install /build/matrix-contracts /build/matrix-compute-settlement

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose default settlement HTTP API port
EXPOSE 8080

# Entrypoint starting settlement REST API server
CMD ["uvicorn", "matrix_settlement.server:app", "--host", "0.0.0.0", "--port", "8080"]
