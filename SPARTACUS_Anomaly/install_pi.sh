#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing system packages ==="
sudo apt-get update -qq
sudo apt-get install -y python3-tk python3-pil python3-pil.imagetk \
                        python3-numpy python3-matplotlib python3-netcdf4 \
                        python3-requests

echo "=== Verifying Python imports ==="
python3 -c "import tkinter, PIL, numpy, matplotlib, netCDF4, requests; print('all imports OK')" \
  || pip3 install --break-system-packages numpy matplotlib netCDF4 requests pillow

echo ""
echo "=== Setup complete ==="
echo "Run:         python3 $SCRIPT_DIR/spartacus_anomaly.py"
echo "Auto-start:  bash $SCRIPT_DIR/setup_autostart.sh"
echo ""
echo "Note: the first run downloads the 1991-2020 climatology (~100 MB, a few minutes)."
