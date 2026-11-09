#!/bin/bash
SCREEN="${1:-0}"
DESKTOP_FILE="$HOME/.config/autostart/party-screen.desktop"

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Party Screen
Exec=python3 $HOME/Lockscreens/PARTY_SCREEN/party_screen.py --screen $SCREEN
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

echo "Autostart configured for screen $SCREEN."
echo "To remove: rm \"$DESKTOP_FILE\""