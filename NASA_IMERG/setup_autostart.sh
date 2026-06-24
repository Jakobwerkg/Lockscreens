#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/nasa-imerg.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=NASA IMERG
Exec=python3 ~/Lockscreens/NASA_IMERG/nasa_imerg.py --screen 0 --wifi-ssid "UPC2254097" --wifi-pass "Kps8hhpkrnak"
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/nasa-imerg.desktop"
echo "Will launch automatically on next login."
