#!/usr/bin/env python3
"""
GoPro Hero 7 stream with DVD-logo screensaver.
Keeps trying to connect. Shows stream when available, screensaver otherwise.
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
KEEPALIVE_INTERVAL = 4

class DVDScreensaver:
    def __init__(self, root):
        self.root = root
        self.root.title("GoPro")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.geometry("1440x900+0+0")
        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.logo = self.canvas.create_text(200, 200, text="DVD", fill="#d4532b",
                                            font=("Arial", 48, "bold"))
        self.dx, self.dy = 4, 3
        self.animate()

    def animate(self):
        self.canvas.move(self.logo, self.dx, self.dy)
        pos = self.canvas.coords(self.logo)
        if pos[0] <= 50 or pos[0] >= 1390:
            self.dx = -self.dx
        if pos[1] <= 40 or pos[1] >= 860:
            self.dy = -self.dy
        self.root.after(30, self.animate)

def is_gopro_reachable():
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", "1", GOPRO_IP],
                           capture_output=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

def connect_wifi():
    subprocess.run(["sudo", "-n", "nmcli", "connection", "up", "stefans gopro 7"],
                   check=False, capture_output=True)
    time.sleep(1)
    if not is_gopro_reachable():
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
        "ffplay", "-fflags", "nobuffer", "-probesize", "100000",
        "-analyzeduration", "1000000", "-sync", "ext",
        "-i", STREAM_URL,
        "-x", "1440", "-y", "900", "-left", "0", "-top", "0"
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

    def check_loop():
        nonlocal player, keepalive, streaming
        if is_gopro_reachable():
            if not streaming:
                print("GoPro found – starting stream")
                connect_wifi()
                subprocess.run(["curl", "-s",
                                f"http://{GOPRO_IP}/gp/gpControl/execute?p1=gpStream&a1=proto_v2&c1=restart"],
                               check=False)
                keepalive = start_keepalive()
                player = start_player()
                streaming = True
                screensaver.canvas.pack_forget()
        else:
            if streaming:
                print("GoPro lost – back to screensaver")
                if player:
                    player.terminate()
                if keepalive:
                    keepalive.terminate()
                player = None
                keepalive = None
                streaming = False
                screensaver.canvas.pack(fill=tk.BOTH, expand=True)
            else:
                connect_wifi()
        root.after(3000, check_loop)

    root.after(1000, check_loop)
    root.mainloop()

if __name__ == "__main__":
    main()