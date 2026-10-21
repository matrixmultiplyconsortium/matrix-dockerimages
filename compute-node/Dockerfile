# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Matrix Compute Node Image (CPU execution engine)
# ------------------------------------------------------------------------------

# --- Stage 1: Build & Dependency Wheel Compilation ---
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install shared contracts library and compute node daemon package together
COPY matrix-contracts /build/matrix-contracts
COPY matrix-compute-node /build/matrix-compute-node
RUN pip install --no-cache-dir --prefix=/install /build/matrix-contracts /build/matrix-compute-node

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create dedicated non-root user
RUN groupadd -g 1000 nodegroup && \
    useradd -u 1000 -g nodegroup -s /bin/bash -m nodeuser

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

USER nodeuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose default gRPC P2P compute port
EXPOSE 50051

# Default entrypoint starts the worker daemon
ENTRYPOINT ["matrix-compute-node"]
CMD []
