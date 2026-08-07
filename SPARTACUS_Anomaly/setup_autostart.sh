#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREEN="${1:-0}"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/spartacus-anomaly.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=SPARTACUS Anomaly
Exec=python3 $SCRIPT_DIR/spartacus_anomaly.py --screen $SCREEN
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/spartacus-anomaly.desktop (screen $SCREEN)"
echo "Will launch automatically on next login."
