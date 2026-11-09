#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing system packages for Hydro ==="
sudo apt-get update -qq
sudo apt-get install -y python3-tk python3-pil python3-requests

echo "=== Installing Python packages ==="
pip3 install --break-system-packages pillow requests 2>/dev/null || pip3 install pillow requests

echo ""
echo "=== Hydro setup complete ==="
echo "Run:         python3 $SCRIPT_DIR/hydro.py --screen 0"
echo "             (edit --screen 0/1 and --images URLs as needed)"
echo "Auto-start:  bash $SCRIPT_DIR/setup_autostart.sh"
