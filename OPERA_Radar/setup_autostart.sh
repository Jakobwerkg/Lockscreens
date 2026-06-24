#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/opera-radar.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=OPERA Radar
Exec=python3 $SCRIPT_DIR/opera_radar_pi.py --screen 0
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written. Will launch on next login."