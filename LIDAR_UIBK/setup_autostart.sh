#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/lidar-uibk.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=LIDAR UIBK
Exec=python3 $SCRIPT_DIR/lidar_uibk.py --screen 0
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/lidar-uibk.desktop"