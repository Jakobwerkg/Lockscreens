#!/bin/bash
set -e
echo "Installing Chromium for party screen..."
sudo apt update
sudo apt install -y chromium-browser
echo "Done."