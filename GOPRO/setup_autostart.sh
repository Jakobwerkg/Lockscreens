#!/bin/bash
SCREEN="${1:-0}"
DESKTOP_FILE="$HOME/.config/autostart/gopro-stream.desktop"

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=GoPro Stream
Exec=python3 $HOME/Lockscreens/GOPRO/gopro_stream.py --screen $SCREEN
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

echo "Autostart configured for screen $SCREEN."
echo "To remove: rm \"$DESKTOP_FILE\""