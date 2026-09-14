# Matrix Settlement Layer Docker Image

Container definition for the `matrix-compute-settlement` economic engine.

## Overview

The settlement layer manages:
- Lightning Network L402 HODL invoice generation and settlement.
- 2% platform routing fee retention.
- Worker bond staking ledger and cryptographic fraud proof slashing (`FreivaldsFraudProof`).

## Build

From the root of the `DistributedMatrixMultiply` workspace:

```bash
docker build -f matrix-dockerimages/settlement/Dockerfile -t matrix-settlement:latest .
```

## Running the Settlement Layer

```bash
docker run -d \
  --name matrix-settlement \
  -p 8080:8080 \
  -e MATRIX_SETTLEMENT_HOST="0.0.0.0" \
  -e MATRIX_SETTLEMENT_PORT=8080 \
  -e MATRIX_SETTLEMENT_SECRET_KEY="settlement_secret_key_dev" \
  matrix-settlement:latest
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MATRIX_SETTLEMENT_HOST` | Host interface to bind HTTP API | `0.0.0.0` |
| `MATRIX_SETTLEMENT_PORT` | Port for settlement API | `8080` |
| `MATRIX_SETTLEMENT_SECRET_KEY` | Secret HMAC key for Macaroon minting and verification | `settlement_secret_key_dev` |
| `MATRIX_SETTLEMENT_PLATFORM_FEE_PERCENT` | Platform fee fraction deducted on settlement | `0.02` (2%) |
| `MATRIX_SETTLEMENT_LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) | `INFO` |

*Note: The settlement layer implementation is actively being developed separately. This image structure will automatically bind to the implementation once source files are added.*
