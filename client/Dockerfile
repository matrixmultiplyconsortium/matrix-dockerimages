# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Matrix Consumer Client / Orchestrator Image (matrix-compute-sdk)
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

# Install consumer SDK package
COPY matrix-compute-sdk /build/matrix-compute-sdk
RUN pip install --no-cache-dir --prefix=/install /build/matrix-compute-sdk

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create a dedicated non-root user and group
RUN groupadd -g 1000 matrixgroup && \
    useradd -u 1000 -g matrixgroup -s /bin/bash -m matrixuser

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

# Prepare workspace directory for matrix IO
RUN mkdir -p /app/data && chown -R matrixuser:matrixgroup /app

USER matrixuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# CLI entrypoint for matrix-compute
ENTRYPOINT ["matrix-compute"]
CMD ["--help"]
