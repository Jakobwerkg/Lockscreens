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
ExecStart=/usr/bin/python3 $REPO/OPERA_Radar/opera_radar_pi.py --screen 0
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
ExecStart=/usr/bin/python3 $REPO/TAWES_UIBK/tawes_uibk.py --screen 1
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload

# allow services to start at boot without an active login session
loginctl enable-linger "$USER"

echo ""
echo "=== Enabling both display services ==="
systemctl --user enable --now opera-radar
systemctl --user enable --now tawes-uibk

echo ""
echo "=== Done ==="
echo ""
echo "  OPERA Radar → screen 0 (left/primary)"
echo "  TAWES UIBK  → screen 1 (right/secondary)"
echo ""
echo "  To swap screens, edit --screen values in $SYSTEMD_DIR/*.service"
echo "  then run: systemctl --user daemon-reload && systemctl --user restart opera-radar tawes-uibk"
