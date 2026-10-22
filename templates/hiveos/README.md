# HiveOS 1-Click Custom Miner Integration

This directory contains the HiveOS custom miner scripts and flight sheet template for running `matrix-worker` on GPU mining rigs.

## Integration Files

- `flightsheet.json`: Flight Sheet template configuring `%WAL%` as the Lightning payout address and `%URL%` as the Nostr relay endpoint.
- `h-manifest.conf`: Custom miner manifest metadata (`CUSTOM_NAME`, `CUSTOM_VERSION`, log and config locations).
- `h-config.sh`: Generates `worker.conf` from HiveOS user config and wallet arguments.
- `h-run.sh`: Execution wrapper running the worker container or local python daemon.
- `h-stats.sh`: Telemetry provider reporting temperatures, fan speeds, and TFLOPS compute output back to the HiveOS web dashboard.

## Deployment on HiveOS

1. In HiveOS Web Dashboard, navigate to **Flight Sheets** -> **Add Flight Sheet**.
2. Select Coin: `CUSTOM`, Miner: `custom`.
3. Fill Custom Miner configuration:
   - Miner name: `matrix-worker`
   - Installation URL / Package: `file:///hive/miners/custom/matrix-worker`
   - Wallet and worker template: `%WAL%`
   - Pool server: `%URL%`
4. Apply Flight Sheet to mining rigs.

## Note
All templates are committed strictly locally. Do not push or publish to external registries.
