#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/foto-webcam.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Foto-Webcam
Exec=python3 ~/Lockscreens/Foto_Webcam/foto_webcam.py --screen 1 --wifi-ssid "UPC2254097" --wifi-pass "Kps8hhpkrnak"
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/foto-webcam.desktop"
echo "Will launch automatically on next login."
