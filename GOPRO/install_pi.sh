#!/bin/bash
set -e
echo "Installing dependencies for GoPro stream..."
sudo apt update
sudo apt install -y ffmpeg curl network-manager
echo "Done."