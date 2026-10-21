# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Matrix Discovery Relay Image (matrix-compute-relay)
# ------------------------------------------------------------------------------

# --- Stage 1: Build & Dependency Wheel Compilation ---
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install shared contracts library and relay package together
COPY matrix-contracts /build/matrix-contracts
COPY matrix-compute-relay /build/matrix-compute-relay
RUN pip install --no-cache-dir --prefix=/install /build/matrix-contracts /build/matrix-compute-relay

# --- Stage 2: Lean Runtime Container ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create dedicated non-root user
RUN groupadd -g 1000 relaygroup && \
    useradd -u 1000 -g relaygroup -s /bin/bash -m relayuser

# Copy installed Python packages and executables from builder
COPY --from=builder /install /usr/local

USER relayuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose default Nostr discovery relay WebSocket port
EXPOSE 8008

# Default command to run the discovery relay
CMD ["python", "-m", "matrix_relay"]
