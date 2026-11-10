#!/usr/bin/env python3
"""
GoPro stream with smooth DVD screensaver and robust reconnect.
True fullscreen, no top bar.
"""

import argparse
import subprocess
import time
import os
import sys
import tkinter as tk
import threading

GOPRO_SSID = "stefans gopro 7"
GOPRO_PASSWORD = "MwJ-rdn-Qy7"
GOPRO_IP = "10.5.5.9"
STREAM_URL = "udp://10.5.5.100:8554?overrun_nonfatal=1&fifo_size=100000"
KEEPALIVE_INTERVAL = 5

class DVDScreensaver:
    def __init__(self, root):
        self.root = root
        self.root.title("GoPro")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.geometry("1440x900+0+0")
        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.logo = self.canvas.create_text(300, 300, text="DVD", fill="#d4532b",
                                            font=("Arial", 60, "bold"))
        self.dx, self.dy = 7, 5
        self.animate()

    def animate(self):
        self.canvas.move(self.logo, self.dx, self.dy)
        x, y = self.canvas.coords(self.logo)
        if x <= 90 or x >= 1350:
            self.dx = -self.dx
        if y <= 60 or y >= 840:
            self.dy = -self.dy
        self.root.after(16, self.animate)

def is_reachable():
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", "2", GOPRO_IP],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False

def ensure_wifi():
    status = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"],
                            capture_output=True, text=True).stdout
    if "wlan1:connected" in status:
        return
    print("Connecting to GoPro WiFi...")
    subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", "stefans gopro 7"],
                   check=False, capture_output=True)
    subprocess.run([
        "sudo", "-n", "nmcli", "connection", "add",
        "type", "wifi", "con-name", "stefans gopro 7",
        "ifname", "wlan1", "ssid", GOPRO_SSID,
        "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", GOPRO_PASSWORD
    ], check=False, capture_output=True)
    subprocess.run(["sudo", "-n", "nmcli", "connection", "up", "stefans gopro 7"],
                   check=False, capture_output=True)
    time.sleep(4)

def start_keepalive():
    cmd = f'''while true; do
  curl -s --max-time 3 "http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart" > /dev/null
  sleep {KEEPALIVE_INTERVAL}
done'''
    return subprocess.Popen(["bash", "-c", cmd],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
        "-fs",
        "-x", "1440", "-y", "900"
    ]
    return subprocess.Popen(cmd, env=env)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()

    root = tk.Tk()
    screensaver = DVDScreensaver(root)

    player = None
    keepalive = None
    streaming = False

    def monitor():
        nonlocal player, keepalive, streaming
        ensure_wifi()
        if is_reachable():
            if not streaming:
                print("GoPro reachable – starting stream")
                subprocess.run(["curl", "-s", "--max-time", "3",
                                f"http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart"],
                               check=False)
                time.sleep(1)
                keepalive = start_keepalive()
                player = start_player()
                streaming = True
                screensaver.canvas.pack_forget()
        else:
            if streaming:
                print("GoPro lost")
                if player:
                    player.terminate()
                    try:
                        player.wait(timeout=2)
                    except Exception:
                        pass
                if keepalive:
                    keepalive.terminate()
                player = None
                keepalive = None
                streaming = False
                screensaver.canvas.pack(fill=tk.BOTH, expand=True)
        root.after(4000, monitor)

    root.after(2000, monitor)
    root.mainloop()

if __name__ == "__main__":
    main()