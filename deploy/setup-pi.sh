#!/usr/bin/env bash
# setup-pi.sh — One-time setup for Ficio on Raspberry Pi 5
# Run as the 'pi' user: bash setup-pi.sh
set -euo pipefail

GITHUB_REPO="davidfarag720-oss/RAS_PI_CODE_ITER_3"
INSTALL_DIR="/home/pi/vegetable-slicer"
PI_USER="${USER:-pi}"

echo "============================================"
echo " Ficio Vegetable Slicer — Pi Setup"
echo "============================================"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────────
echo "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 python3-venv python3-pip \
    chromium-browser \
    curl jq \
    libatlas-base-dev \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
    libcap2-bin

echo "  System dependencies installed."

# ── 2. GitHub CLI ─────────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
    echo "Installing GitHub CLI..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt-get update -qq && sudo apt-get install -y gh
    echo "  gh CLI installed."
fi

# ── 3. GitHub authentication ─────────────────────────────────────────────────
if ! gh auth status &>/dev/null; then
    echo ""
    echo "Please log in to GitHub (needed for downloading releases):"
    gh auth login
fi
echo "  GitHub authentication: OK"

# ── 4. Create install directory and download latest release ──────────────────
echo ""
echo "Downloading latest release from GitHub..."
mkdir -p "$INSTALL_DIR"

LATEST_TAG=$(gh release view --repo "$GITHUB_REPO" --json tagName -q '.tagName')
echo "  Latest release: $LATEST_TAG"

mkdir -p /tmp/ficio-setup
gh release download "$LATEST_TAG" \
    --repo "$GITHUB_REPO" \
    --pattern '*.tar.gz' \
    --dir /tmp/ficio-setup

tar xzf /tmp/ficio-setup/*.tar.gz -C "$INSTALL_DIR" --strip-components=1
rm -rf /tmp/ficio-setup
echo "  Release extracted to $INSTALL_DIR"

# ── 5. Patch config.json install path ────────────────────────────────────────
if [ -f "$INSTALL_DIR/config.json" ]; then
    sed -i "s|/home/dfarag/RAS_PI_CODE_ITER_3|$INSTALL_DIR|g" "$INSTALL_DIR/config.json"
    sed -i "s|/home/dfarag/vegetable-slicer|$INSTALL_DIR|g" "$INSTALL_DIR/config.json"
    echo "  Patched config.json install paths."
fi

# ── 6. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "Setting up Python virtual environment..."
echo "  (ultralytics/torch may take 10-20 minutes on first install)"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
echo "  Python venv ready."

# ── 7. Data directories ───────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"/{data/cv_images,logs,models,assets/ui}

# ── 8. Make scripts executable ───────────────────────────────────────────────
chmod +x "$INSTALL_DIR/deploy/ficio-updater.sh"
chmod +x "$INSTALL_DIR/deploy/setup-pi.sh"
chmod +x "$INSTALL_DIR/deploy/deploy.sh"

# ── 9. Install systemd services ──────────────────────────────────────────────
echo ""
echo "Installing systemd services..."
sudo cp "$INSTALL_DIR/deploy/systemd/ficio-api.service"      /etc/systemd/system/
sudo cp "$INSTALL_DIR/deploy/systemd/ficio-kiosk.service"    /etc/systemd/system/
sudo cp "$INSTALL_DIR/deploy/systemd/ficio-updater.service"  /etc/systemd/system/
sudo cp "$INSTALL_DIR/deploy/systemd/ficio-updater.timer"    /etc/systemd/system/
# Patch user and paths into service files
sudo sed -i "s|User=pi|User=$PI_USER|g" /etc/systemd/system/ficio-api.service
sudo sed -i "s|User=pi|User=$PI_USER|g" /etc/systemd/system/ficio-kiosk.service
sudo sed -i "s|FICIO_USER=pi|FICIO_USER=$PI_USER|g" /etc/systemd/system/ficio-updater.service
sudo sed -i "s|/home/pi|/home/$PI_USER|g" /etc/systemd/system/ficio-api.service
sudo sed -i "s|/home/pi|/home/$PI_USER|g" /etc/systemd/system/ficio-kiosk.service
sudo sed -i "s|/home/pi|/home/$PI_USER|g" /etc/systemd/system/ficio-updater.service
sudo systemctl daemon-reload
sudo systemctl enable ficio-api.service
sudo systemctl enable ficio-kiosk.service
sudo systemctl enable ficio-updater.timer
echo "  Services enabled."

# ── 10. Kiosk exit keybinding (Ctrl+Alt+Q) ───────────────────────────────────
echo ""
echo "Configuring Ctrl+Alt+Q keybinding to exit kiosk..."
KILL_CMD="pkill -f chromium-browser"

# labwc (RPi OS Bookworm default Wayland compositor)
LABWC_DIR="$HOME/.config/labwc"
LABWC_RC="$LABWC_DIR/rc.xml"
if [ -d "$LABWC_DIR" ] || command -v labwc &>/dev/null; then
    mkdir -p "$LABWC_DIR"
    if [ ! -f "$LABWC_RC" ]; then
        cat > "$LABWC_RC" <<'EOF'
<?xml version="1.0"?>
<labwc_config>
  <keyboard>
    <keybind key="C-A-q">
      <action name="Execute"><command>pkill -f chromium-browser</command></action>
    </keybind>
  </keyboard>
</labwc_config>
EOF
    elif ! grep -q "C-A-q" "$LABWC_RC"; then
        # Insert before closing tag
        sed -i 's|</keyboard>|  <keybind key="C-A-q">\n      <action name="Execute"><command>pkill -f chromium-browser</command></action>\n    </keybind>\n  </keyboard>|' "$LABWC_RC" 2>/dev/null || \
        sed -i 's|</labwc_config>|  <keyboard>\n    <keybind key="C-A-q">\n      <action name="Execute"><command>pkill -f chromium-browser</command></action>\n    </keybind>\n  </keyboard>\n</labwc_config>|' "$LABWC_RC"
    fi
    echo "  labwc keybinding configured."
fi

# openbox / LXDE (older RPi OS with X11)
OPENBOX_RC="$HOME/.config/openbox/lxde-pi-rc.xml"
if [ -f "$OPENBOX_RC" ] && ! grep -q "C-A-q" "$OPENBOX_RC"; then
    sed -i 's|</keyboard>|  <keybind key="C-A-q">\n      <action name="Execute"><execute>pkill -f chromium-browser</execute></action>\n    </keybind>\n  </keyboard>|' "$OPENBOX_RC"
    echo "  openbox keybinding configured."
fi

# ── 11. Start services ────────────────────────────────────────────────────────
echo ""
echo "Starting services..."
sudo systemctl start ficio-api.service
sudo systemctl start ficio-updater.timer

echo ""
echo "Waiting for API to be ready..."
for i in $(seq 1 15); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  API is up."
        break
    fi
    sleep 2
done

echo ""
echo "============================================"
echo " Setup Complete!"
echo "============================================"
echo ""
echo "  App:         http://localhost:8000"
echo "  API docs:    http://localhost:8000/docs"
echo "  Health:      http://localhost:8000/health"
echo ""
echo "  Exit kiosk:  Ctrl+Alt+Q"
echo ""
echo " Useful commands:"
echo "  sudo systemctl status ficio-api          — check API status"
echo "  sudo systemctl status ficio-kiosk        — check kiosk status"
echo "  journalctl -u ficio-api -f               — stream API logs"
echo "  journalctl -u ficio-updater -f           — stream updater logs"
echo "  sudo systemctl start ficio-updater       — check for updates now"
echo "  sudo systemctl disable ficio-kiosk       — disable kiosk on boot"
echo "  sudo systemctl enable ficio-kiosk        — re-enable kiosk on boot"
echo ""
echo " Kiosk will launch automatically on next reboot."
echo " To launch it now:  sudo systemctl start ficio-kiosk"
