# Matrix Compute Node Docker Images

Contains container definitions for the worker daemon (`matrix-compute-node`).

Two variants are provided:
1. `Dockerfile`: CPU execution engine using NumPy and standard CPU matrix multiplication.
2. `Dockerfile.gpu`: NVIDIA CUDA 12.x execution engine utilizing PyTorch with NVML attestation support.

## Building the Images

From the root of the `DistributedMatrixMultiply` workspace:

### CPU Variant
```bash
docker build -f matrix-dockerimages/compute-node/Dockerfile -t matrix-compute-node:latest .
```

### GPU Variant
```bash
docker build -f matrix-dockerimages/compute-node/Dockerfile.gpu -t matrix-compute-node:gpu .
```

## Running the Compute Node

### CPU Node
```bash
docker run -d \
  --name matrix-compute-node \
  -p 50051:50051 \
  -e MATRIX_WORKER_NOSTR_RELAYS='["ws://relay:8008"]' \
  -e MATRIX_WORKER_SETTLEMENT_API_URL="http://settlement:8080" \
  matrix-compute-node:latest
```

### GPU Node (NVIDIA Container Toolkit)
Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed on the host.

```bash
docker run -d \
  --name matrix-compute-node-gpu \
  --gpus all \
  -p 50051:50051 \
  -e MATRIX_WORKER_GPU_DEVICE_INDEX=0 \
  -e MATRIX_WORKER_DTYPE_PREFERENCE="fp16" \
  -e MATRIX_WORKER_NOSTR_RELAYS='["ws://relay:8008"]' \
  -e MATRIX_WORKER_SETTLEMENT_API_URL="http://settlement:8080" \
  matrix-compute-node:gpu
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MATRIX_WORKER_P2P_HOST` | Host interface to bind gRPC server | `0.0.0.0` |
| `MATRIX_WORKER_P2P_PORT` | Port for incoming gRPC compute tasks | `50051` |
| `MATRIX_WORKER_PRIVKEY_HEX` | 32-byte Secp256k1 private key hex for signing | Ephemeral random |
| `MATRIX_WORKER_SATS_PER_GFLOP` | Price rate in satoshis per GFLOP | `0.0005` |
| `MATRIX_WORKER_MIN_TASK_SATS` | Minimum price floor per task in satoshis | `10` |
| `MATRIX_WORKER_NOSTR_RELAYS` | JSON array of discovery relay WebSocket URLs | `["ws://127.0.0.1:8008"]` |
| `MATRIX_WORKER_SETTLEMENT_API_URL` | Base URL for settlement layer | `http://127.0.0.1:8080` |
| `MATRIX_WORKER_SETTLEMENT_VERIFICATION_KEY` | Secret HMAC verification key | `settlement_secret_key_dev` |
| `MATRIX_WORKER_GPU_DEVICE_INDEX` | Index of GPU to attest and use | `0` |
| `MATRIX_WORKER_DTYPE_PREFERENCE` | Preferred precision (`fp32`, `fp16`, `bf16`) | `fp32` |
