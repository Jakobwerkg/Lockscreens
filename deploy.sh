#!/usr/bin/env bash
# Usage: bash deploy.sh <pi-user@hostname-or-ip> [repo-path-on-pi]
# Example: bash deploy.sh pi@bildschirm1.local
#          bash deploy.sh pi@192.168.0.42 ~/my-lockscreens
set -e

if [ -z "$1" ]; then
  echo "Usage: bash deploy.sh <pi-user@hostname-or-ip> [repo-path-on-pi]"
  echo "Example: bash deploy.sh pi@bildschirm1.local"
  exit 1
fi

PI=$1
REPO_DIR=${2:-~/Lockscreens}   # default clone path on the Pi, override with 2nd arg

echo "=== Pushing to origin ==="
git -C "$(dirname "$0")" push

echo "=== Deploying to $PI ==="
ssh "$PI" "
  cd $REPO_DIR && git pull &&
  systemctl --user restart opera-radar.service 2>/dev/null | true &&
  systemctl --user restart tawes-uibk.service  2>/dev/null | true &&
  echo 'Done.'
"
