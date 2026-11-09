#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/hydro.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Hydro
Exec=python3 $SCRIPT_DIR/hydro.py --screen 1
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Autostart entry written → $HOME/.config/autostart/hydro.desktop"
echo "Will launch automatically on next login (edit file to change --screen or add --images)."
