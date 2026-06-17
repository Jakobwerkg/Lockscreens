#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Installing system packages ==="
sudo apt-get update -qq
sudo apt-get install -y python3-tk python3-pil python3-pil.imagetk python3-requests
echo "=== Installing Python packages ==="
pip3 install --break-system-packages pillow requests 2>/dev/null || pip3 install pillow requests
mkdir -p "$SCRIPT_DIR/cache"
echo ""
echo "Run:  python3 $SCRIPT_DIR/opera_radar_pi.py"
echo "Auto-start:  bash $SCRIPT_DIR/setup_autostart.sh"
