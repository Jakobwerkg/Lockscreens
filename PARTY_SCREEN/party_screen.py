#!/usr/bin/env python3
"""
Party screen for Lockscreens.
Opens the come-inside /screen page fullscreen in Chromium.
"""

import argparse
import subprocess
import os
import sys

# Change this to the hosting Pi's IP or your domain
SCREEN_URL = "http://192.168.0.103:8080/screen"
# Or use the public domain:
# SCREEN_URL = "https://sommerfest-2026.com/screen"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()

    env = os.environ.copy()
    env["DISPLAY"] = ":0"

    # Kill any existing chromium so we start clean
    subprocess.run(["pkill", "-f", "chromium"], check=False)

    cmd = [
        "chromium-browser",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-features=TranslateUI",
        "--check-for-update-interval=31536000",
        SCREEN_URL,
    ]

    print(f"Starting party screen on display (screen {args.screen})")
    subprocess.run(cmd, env=env)

if __name__ == "__main__":
    main()