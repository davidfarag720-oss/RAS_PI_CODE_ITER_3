#!/usr/bin/env bash
#
# restart-ficio-services.sh
# Performs a "cold" service restart sequence that mimics:
#   stop kiosk -> stop api -> short settle delay -> start api -> start kiosk
#
# Usage:
#   sudo /home/<user>/vegetable-slicer/deploy/restart-ficio-services.sh
#

set -euo pipefail

echo "[ficio-restart] Stopping kiosk..."
systemctl stop ficio-kiosk.service

echo "[ficio-restart] Stopping API..."
systemctl stop ficio-api.service

# Short settle window is intentional: allows serial device teardown/release
# to complete before API re-opens the UART device.
echo "[ficio-restart] Waiting for UART/serial stack to settle..."
sleep 2

echo "[ficio-restart] Starting API..."
systemctl start ficio-api.service

echo "[ficio-restart] Waiting for API health..."
healthy=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null; then
        healthy=true
        break
    fi
    sleep 1
done

if [ "$healthy" != "true" ]; then
    echo "[ficio-restart][ERROR] API health check timeout after 30 seconds" >&2
    exit 1
fi

# Kiosk startup is deferred until API health is confirmed to avoid frontend
# retries against an API that is still initializing STM32 comms.
echo "[ficio-restart] Starting kiosk..."
systemctl start ficio-kiosk.service

echo "[ficio-restart] Done."
