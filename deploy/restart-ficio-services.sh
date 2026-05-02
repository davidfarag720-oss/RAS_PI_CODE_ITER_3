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
systemctl stop ficio-kiosk.service || true

echo "[ficio-restart] Stopping API..."
systemctl stop ficio-api.service || true

echo "[ficio-restart] Waiting for UART/serial stack to settle..."
sleep 2

echo "[ficio-restart] Starting API..."
systemctl start ficio-api.service

echo "[ficio-restart] Waiting for API health..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null; then
        break
    fi
    sleep 1
done

echo "[ficio-restart] Starting kiosk..."
systemctl start ficio-kiosk.service || true

echo "[ficio-restart] Done."
