#!/usr/bin/env bash
# ficio-updater.sh — Runs on Pi as root via systemd timer
# Checks GitHub for a new release, downloads, swaps atomically, restarts services.
# Rolls back automatically if the new version fails the health check.
set -euo pipefail

FICIO_USER="${FICIO_USER:-${SUDO_USER:-pi}}"
INSTALL_DIR="/home/${FICIO_USER}/vegetable-slicer"
GITHUB_REPO="davidfarag720-oss/RAS_PI_CODE_ITER_3"
BACKUP_DIR="/home/${FICIO_USER}/vegetable-slicer-backup"
TEMP_DIR="/tmp/ficio-update-$$"

log() { echo "[ficio-updater] $*" | systemd-cat -t ficio-updater -p info; echo "[ficio-updater] $*"; }
log_err() { echo "[ficio-updater] ERROR: $*" | systemd-cat -t ficio-updater -p err; echo "[ficio-updater] ERROR: $*" >&2; }

cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

# ── 1. Read local version ─────────────────────────────────────────────────────
LOCAL_VERSION=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "0.0.0")
log "Local version: $LOCAL_VERSION"

# ── 2. Fetch latest release tag from GitHub ───────────────────────────────────
if ! LATEST_TAG=$(sudo -u "$FICIO_USER" gh release view --repo "$GITHUB_REPO" --json tagName -q '.tagName' 2>/dev/null); then
    log_err "Failed to reach GitHub (offline?). Skipping update check."
    exit 0
fi
LATEST_VERSION="${LATEST_TAG#v}"  # strip leading 'v'

if [ "$LATEST_VERSION" = "$LOCAL_VERSION" ]; then
    log "Already up to date (v$LOCAL_VERSION)."
    exit 0
fi

log "New version available: $LOCAL_VERSION → $LATEST_VERSION"

# ── 3. Download tarball ───────────────────────────────────────────────────────
mkdir -p "$TEMP_DIR"
chown "$FICIO_USER:$FICIO_USER" "$TEMP_DIR"
log "Downloading v$LATEST_VERSION..."
if ! sudo -u "$FICIO_USER" gh release download "$LATEST_TAG" \
        --repo "$GITHUB_REPO" \
        --pattern '*.tar.gz' \
        --dir "$TEMP_DIR" 2>&1; then
    log_err "Download failed. Skipping update."
    exit 0
fi

TARBALL=$(ls "$TEMP_DIR"/*.tar.gz 2>/dev/null | head -1)
if [ -z "$TARBALL" ]; then
    log_err "No tarball found after download."
    exit 0
fi

# ── 4. Verify tarball integrity ───────────────────────────────────────────────
if ! gzip -t "$TARBALL" 2>/dev/null; then
    log_err "Tarball is corrupt. Skipping update."
    exit 0
fi

# ── 5. Extract and carry forward user data ────────────────────────────────────
mkdir -p "$TEMP_DIR/extracted"
tar xzf "$TARBALL" -C "$TEMP_DIR/extracted" --strip-components=1
log "Extraction complete."

# Carry forward existing venv (speeds up pip install)
if [ -d "$INSTALL_DIR/venv" ]; then
    cp -a "$INSTALL_DIR/venv" "$TEMP_DIR/extracted/venv"
fi
# Carry forward user's config.json (may have been customised on Pi)
if [ -f "$INSTALL_DIR/config.json" ]; then
    cp "$INSTALL_DIR/config.json" "$TEMP_DIR/extracted/config.json"
fi
# Carry forward data directory (CV images, logs, database)
if [ -d "$INSTALL_DIR/data" ]; then
    cp -a "$INSTALL_DIR/data" "$TEMP_DIR/extracted/data"
fi

chown -R "$FICIO_USER:$FICIO_USER" "$TEMP_DIR/extracted"

# ── 6. Atomic swap ────────────────────────────────────────────────────────────
log "Applying update..."
[ -d "$BACKUP_DIR" ] && rm -rf "$BACKUP_DIR"
mv "$INSTALL_DIR" "$BACKUP_DIR"
mv "$TEMP_DIR/extracted" "$INSTALL_DIR"

# ── 7. Install updated Python dependencies ────────────────────────────────────
log "Installing dependencies..."
sudo -u "$FICIO_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt" 2>&1 || true

# ── 8. Restart API and health check ──────────────────────────────────────────
log "Restarting API service..."
systemctl restart ficio-api.service

log "Waiting for health check..."
HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 2
done

if $HEALTHY; then
    # ── 9. Success ────────────────────────────────────────────────────────────
    rm -rf "$BACKUP_DIR"
    log "Update to v$LATEST_VERSION successful."
    # Restart kiosk if it's active so it picks up any frontend changes
    if systemctl is-active --quiet ficio-kiosk.service; then
        systemctl restart ficio-kiosk.service
    fi
else
    # ── 10. Rollback ─────────────────────────────────────────────────────────
    log_err "Health check failed after update to v$LATEST_VERSION. Rolling back to v$LOCAL_VERSION..."
    systemctl stop ficio-api.service || true
    rm -rf "$INSTALL_DIR"
    mv "$BACKUP_DIR" "$INSTALL_DIR"
    systemctl start ficio-api.service
    log_err "Rollback complete. Staying on v$LOCAL_VERSION."
    exit 1
fi
