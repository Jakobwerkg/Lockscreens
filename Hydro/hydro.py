#!/usr/bin/env python3
"""
hydro.py – Main Hydro screen script (with --screen support)

- Fullscreen on chosen monitor (--screen 0 or 1)
- 1400x900 resolution
- Calls DataUpdater + generate_charts in background
- Status bar at bottom
- Escape/Q to quit
"""

import argparse
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

from data_updater import DataUpdater
from generate_charts import generate_all_charts

GENERATED_DIR = Path("generated")
RESOLUTION = (1400, 900)
SLIDE_SEC = 8
DATA_UPDATE_INTERVAL = 300
CHART_UPDATE_INTERVAL = 300


def _screen_geometry(index: int, root: tk.Tk):
    """Get geometry of monitor index using xrandr."""
    try:
        out = subprocess.check_output(["xrandr"], text=True, stderr=subprocess.DEVNULL)
        monitors = sorted(
            (int(m.group(3)), int(m.group(4)), int(m.group(1)), int(m.group(2)))
            for m in re.finditer(r"\bconnected\b.*?(\d+)x(\d+)\+(\d+)\+(\d+)", out)
        )
        if index < len(monitors):
            return monitors[index]
    except Exception:
        pass
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    return (0, 0, sw, sh)


class HydroApp:
    def __init__(self, root, screen_index: int):
        self.root = root
        self.screen_index = screen_index

        self.root.title("Hydro")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda e: self.root.quit())
        self.root.bind("q", lambda e: self.root.quit())

        # Position on correct screen
        sx, sy, sw, sh = _screen_geometry(screen_index, root)
        self.root.overrideredirect(True)
        self.root.geometry(f"{RESOLUTION[0]}x{RESOLUTION[1]}+{sx}+{sy}")

        # Main image
        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        # Status bar
        self.status_label = tk.Label(
            self.root,
            text="Starting...",
            bg="#161b22",
            fg="#8b949e",
            font=("DejaVu Sans Mono", 10),
            anchor="w",
            padx=10
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.images = []
        self.current_idx = 0
        self.photo = None
        self.last_update = None
        self.station_count = 0

        self.updater = DataUpdater()

        self.start_background()
        self.load_images()
        self.show_next()

    # ── Background orchestration ─────────────────────────────────────────────
    def start_background(self):
        threading.Thread(target=self._data_and_chart_loop, daemon=True).start()

    def _data_and_chart_loop(self):
        while True:
            try:
                self.updater.update_current()
                current = self.updater.get_all_current()
                self.station_count = len(current)
                self.last_update = datetime.now()

                generate_all_charts(self.updater)
                self.load_images()
                self.update_status()
            except Exception as e:
                print(f"[hydro] Background error: {e}")
            time.sleep(DATA_UPDATE_INTERVAL)

    # ── UI ───────────────────────────────────────────────────────────────────
    def load_images(self):
        self.images = sorted(GENERATED_DIR.glob("*.png"))

    def update_status(self):
        if not self.last_update:
            text = "Waiting for first update..."
        else:
            text = (f"Last update: {self.last_update.strftime('%H:%M:%S')}  •  "
                    f"Stations: {self.station_count}  •  "
                    f"Charts: {len(self.images)}")
        self.status_label.after(0, lambda: self.status_label.configure(text=text))

    def show_next(self):
        if not self.images:
            self.img_label.configure(
                text="No charts yet\nWaiting for data...",
                fg="#ff6b6b", font=("DejaVu Sans", 16)
            )
            self.root.after(4000, self.show_next)
            return

        img_path = self.images[self.current_idx]
        try:
            pil = Image.open(img_path).convert("RGB")
            pil.thumbnail(RESOLUTION, Image.LANCZOS)
            self.photo = ImageTk.PhotoImage(pil)
            self.img_label.configure(image=self.photo)
        except Exception as e:
            print(f"[hydro] Image error: {e}")

        self.current_idx = (self.current_idx + 1) % len(self.images)
        self.root.after(SLIDE_SEC * 1000, self.show_next)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0,
                        help="Monitor index (0 or 1)")
    args = parser.parse_args()

    root = tk.Tk()
    HydroApp(root, screen_index=args.screen)
    root.mainloop()
