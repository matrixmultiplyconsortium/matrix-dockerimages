# Vast.ai 1-Click Community Worker Template

This template enables Vast.ai host providers to monetize unrented/idle GPU capacity by joining the Distributed Matrix Multiply compute network.

## Deployment Instructions

1. In the Vast.ai Console or CLI, load `template.json`.
2. Configure your environment variables:
   - `MATRIX_WORKER_PAYOUT_ADDRESS`: Your Lightning Address or LNURL (e.g. `yourname@getalby.com` or `yourname@phoenix.me`).
   - `MATRIX_WORKER_NOSTR_RELAYS`: `wss://relay.matrixcompute.io`
   - `MATRIX_WORKER_SETTLEMENT_API_URL`: `http://settlement.matrixcompute.io:8000`
   - `MATRIX_WORKER_NAT_MODE`: `reverse_tunnel` (allows unrented rigs to work behind strict NAT without port forwarding).
3. Start the instance. Payouts are streamed via Lightning Network as matrix tile multiplication jobs are computed and verified via Freivalds probabilistic checks.

## Note
All templates are committed strictly locally. Do not push or publish to external registries.
