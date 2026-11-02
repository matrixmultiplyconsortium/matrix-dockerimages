# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Matrix Compute MCP Server & High-Level AI Primitives Image (matrix-compute-mcp)
# ------------------------------------------------------------------------------

# --- Stage 1: Build & Dependency Wheel Compilation ---
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install shared contracts, consumer SDK, and MCP server package together
COPY matrix-contracts /build/matrix-contracts
COPY matrix-compute-sdk /build/matrix-compute-sdk
COPY matrix-compute-mcp /build/matrix-compute-mcp
RUN pip install --no-cache-dir --prefix=/install \
    websockets \
    /build/matrix-contracts \
    /build/matrix-compute-sdk \
    /build/matrix-compute-mcp

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create a dedicated non-root user and group
RUN groupadd -g 1000 matrixgroup && \
    useradd -u 1000 -g matrixgroup -s /bin/bash -m matrixuser

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

# Prepare workspace directory for matrix tensor IO (.npy, .npz, .safetensors)
RUN mkdir -p /app/data && chown -R matrixuser:matrixgroup /app

USER matrixuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# CLI stdio entrypoint for Model Context Protocol (MCP) clients
ENTRYPOINT ["matrix-compute-mcp"]
CMD []
