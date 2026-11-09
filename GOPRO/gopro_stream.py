#!/usr/bin/env python3
"""
GoPro Hero 7 Black live preview for Lockscreens.
Connects wlan1 to the camera, keeps the stream alive, and displays it fullscreen.
"""

import argparse
import subprocess
import time
import os
import sys

GOPRO_SSID = "stefans gopro 7"
GOPRO_PASSWORD = "MwJ-rdn-Qy7"
GOPRO_IP = "10.5.5.9"
STREAM_URL = "udp://10.5.5.100:8554?overrun_nonfatal=1&fifo_size=100000"
KEEPALIVE_INTERVAL = 4

def connect_wifi():
    print("Connecting wlan1 to GoPro...")
    # Try to bring up existing connection first
    subprocess.run(["sudo", "-n", "nmcli", "connection", "up", "stefans gopro 7"], check=False)
    time.sleep(2)
    # If still not connected, recreate it
    result = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"], capture_output=True, text=True)
    if "wlan1:connected" not in result.stdout:
        subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", "stefans gopro 7"], check=False)
        subprocess.run([
            "sudo", "-n", "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", "stefans gopro 7",
            "ifname", "wlan1",
            "ssid", GOPRO_SSID,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", GOPRO_PASSWORD
        ], check=False)
        subprocess.run(["sudo", "-n", "nmcli", "connection", "up", "stefans gopro 7"], check=False)
    time.sleep(3)
def start_keepalive():
    cmd = f'''while true; do
  curl -s "http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart" > /dev/null
  sleep {KEEPALIVE_INTERVAL}
done'''
    return subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_player():
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    cmd = [
        "ffplay",
        "-fflags", "nobuffer",
        "-probesize", "100000",
        "-analyzeduration", "1000000",
        "-sync", "ext",
        "-i", STREAM_URL,
        "-x", "1440",
        "-y", "900",
        "-left", "0",
        "-top", "0"
    ]
    return subprocess.Popen(cmd, env=env)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0, help="Screen index (for compatibility)")
    args = parser.parse_args()

    print(f"Starting GoPro stream (screen {args.screen})")
    connect_wifi()

    # Start stream once
    subprocess.run(["curl", "-s", f"http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart"], check=False)

    keepalive = start_keepalive()
    player = start_player()

    try:
        player.wait()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        keepalive.terminate()
        player.terminate()

if __name__ == "__main__":
    main()