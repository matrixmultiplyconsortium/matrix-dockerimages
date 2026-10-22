# RunPod 1-Click Community Worker Pod Template

This template enables RunPod host providers to run `matrix-compute-node` on unrented GPU pods.

## Pod Setup

1. In the RunPod Templates UI or API, import `template.json`.
2. Configure the environment variables:
   - `MATRIX_WORKER_PAYOUT_ADDRESS`: Your Lightning Address or LNURL.
   - `MATRIX_WORKER_NOSTR_RELAYS`: `wss://relay.matrixcompute.io`
   - `MATRIX_WORKER_SETTLEMENT_API_URL`: `http://settlement.matrixcompute.io:8000`
   - `MATRIX_WORKER_NAT_MODE`: `reverse_tunnel`
3. Launch pod. The worker automatically registers with the Nostr relay and receives matrix tiles via outbound reverse gRPC tunnel.

## Note
All templates are committed strictly locally. Do not push or publish to external registries.
