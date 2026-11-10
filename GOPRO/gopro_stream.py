#!/usr/bin/env python3
"""
GoPro stream – reliable version.
Uses the simple connect/start that worked before.
Shows a lightweight screensaver only when the camera is offline.
Screen position is controlled by --screen (0 = left, 1 = right).
"""

import argparse
import subprocess
import time
import os
import sys
import tkinter as tk

GOPRO_SSID = "stefans gopro 7"
GOPRO_PASSWORD = "MwJ-rdn-Qy7"
GOPRO_IP = "10.5.5.9"
STREAM_URL = "udp://10.5.5.100:8554?overrun_nonfatal=1&fifo_size=100000"
KEEPALIVE_INTERVAL = 4

def connect_wifi():
    print("Connecting wlan1 to GoPro...")
    subprocess.run([
        "sudo", "-n", "nmcli", "device", "wifi", "connect",
        GOPRO_SSID, "password", GOPRO_PASSWORD, "ifname", "wlan1"
    ], check=False)
    time.sleep(3)

def is_reachable():
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "3",
             f"http://{GOPRO_IP}/gp/gpControl/status"],
            capture_output=True, timeout=4
        )
        return r.returncode == 0 and b"status" in r.stdout
    except Exception:
        return False

def start_keepalive():
    cmd = f'''while true; do
  curl -s "http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart" > /dev/null
  sleep {KEEPALIVE_INTERVAL}
done'''
    return subprocess.Popen(["bash", "-c", cmd],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_player(screen=0):
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    x = 0 if screen == 0 else 1440
    cmd = [
        "ffplay",
        "-fflags", "nobuffer",
        "-probesize", "100000",
        "-analyzeduration", "1000000",
        "-sync", "ext",
        "-i", STREAM_URL,
        "-x", "1440", "-y", "900",
        "-left", str(x), "-top", "0"
    ]
    return subprocess.Popen(cmd, env=env)

def show_screensaver(screen=0):
    root = tk.Tk()
    root.title("GoPro")
    root.configure(bg="black")
    root.attributes("-fullscreen", True)
    root.overrideredirect(True)
    x = 0 if screen == 0 else 1440
    root.geometry(f"1440x900+{x}+0")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    logo = canvas.create_text(400, 300, text="DVD", fill="#d4532b",
                              font=("Arial", 48, "bold"))
    dx = [5]
    dy = [3]

    def move():
        canvas.move(logo, dx[0], dy[0])
        x, y = canvas.coords(logo)
        if x <= 60 or x >= 1380:
            dx[0] = -dx[0]
        if y <= 40 or y >= 860:
            dy[0] = -dy[0]
        root.after(20, move)

    def check():
        if is_reachable():
            root.destroy()
        else:
            root.after(3000, check)

    move()
    root.after(3000, check)
    root.mainloop()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()

    print(f"Starting GoPro stream (screen {args.screen})")

    while True:
        connect_wifi()
        if is_reachable():
            print("GoPro found – starting stream")
            subprocess.run(["curl", "-s",
                            f"http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart"],
                           check=False)
            keepalive = start_keepalive()
            player = start_player(args.screen)
            player.wait()
            keepalive.terminate()
            print("Stream ended")
        else:
            print("GoPro not reachable – screensaver")
            show_screensaver(args.screen)
        time.sleep(2)

if __name__ == "__main__":
    main()