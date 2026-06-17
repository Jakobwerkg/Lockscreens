#!/usr/bin/env bash
# Usage: bash deploy.sh [pi-user@pi-hostname-or-ip]
# Example: bash deploy.sh pi@192.168.1.42
#          bash deploy.sh pi@raspberrypi.local
set -e

PI=${1:-pi@raspberrypi.local}
REPO_DIR=~/Lockscreens   # path on the Pi

echo "=== Pushing to origin ==="
git -C "$(dirname "$0")" push

echo "=== Deploying to $PI ==="
ssh "$PI" "
  cd $REPO_DIR && git pull &&
  systemctl --user restart opera-radar.service 2>/dev/null | true &&
  systemctl --user restart tawes-uibk.service  2>/dev/null | true &&
  echo 'Done.'
"
