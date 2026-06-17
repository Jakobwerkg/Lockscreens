#!/usr/bin/env bash
# Run once on the Pi after cloning the repo.
# Sets up dependencies and systemd user services for both displays.
set -e

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== Installing dependencies ==="
bash "$REPO/OPERA_Radar/install_pi.sh"
bash "$REPO/TAWES_UIBK/install_pi.sh"

echo "=== Creating systemd user services ==="
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/opera-radar.service" << SERVICE
[Unit]
Description=OPERA Radar Display

[Service]
Environment=DISPLAY=:0
ExecStart=/usr/bin/python3 $REPO/OPERA_Radar/opera_radar_pi.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
SERVICE

cat > "$SYSTEMD_DIR/tawes-uibk.service" << SERVICE
[Unit]
Description=TAWES UIBK Display

[Service]
Environment=DISPLAY=:0
ExecStart=/usr/bin/python3 $REPO/TAWES_UIBK/tawes_uibk.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload

# allow services to start at boot without an active login session
loginctl enable-linger "$USER"

echo ""
echo "=== Done. Enable the display you want ==="
echo ""
echo "  OPERA Radar:  systemctl --user enable --now opera-radar"
echo "  TAWES UIBK:   systemctl --user enable --now tawes-uibk"
echo ""
echo "  Note: both are fullscreen — only run one at a time."
