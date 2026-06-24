#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/eumetsat-vis006.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=EUMETSAT VIS006
Exec=python3 $SCRIPT_DIR/eumetsat_vis006.py --screen 1
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/eumetsat-vis006.desktop"