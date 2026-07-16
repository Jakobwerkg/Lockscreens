"""
TAWES UIBK – multi-station fullscreen display
Cycles between stations every 30 seconds.
Full image refresh from server every 10 minutes.
Q / Escape = quit
"""

import argparse
import io
import re
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from PIL import Image, ImageTk
import requests

STATIONS = [
    {"url": "https://ertel2.uibk.ac.at/ertel/tawes_style_001_current.png", "name": "TAWES IBK"},
    {"url": "https://ertel2.uibk.ac.at/ertel/tawes_style_002_current.png", "name": "TAWES Obergurgl"},
    {"url": "https://ertel2.uibk.ac.at/ertel/tawes_style_309_current.png", "name": "FAIR Mast"},
    {"url": "https://ertel2.uibk.ac.at/ertel/berliner.png", "name": "Berliner Huette"},
    
]
SWITCH_SEC   = 15
REFRESH_SEC  = 400  # 10 minutes server refresh


def _screen_geometry(index: int) -> tuple:
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
    return (index * 1920, 0, 1920, 1080)


class TawesApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.stations = [
            {"url": s["url"], "name": s["name"], "photo": None, "last_update": None}
            for s in STATIONS
        ]
        self.current_idx = 0

        self.root.title("TAWES UIBK")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._initial_load()
        self.root.after(SWITCH_SEC * 1000, self._switch)
        self._start_refresh(delay_ms=REFRESH_SEC * 1000)

    def _initial_load(self):
        for i in range(len(self.stations)):
            self._download_station(i)
        self._show_current()

    def _download_station(self, idx):
        station = self.stations[idx]
        try:
            resp = requests.get(station["url"], timeout=15)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            sw = self.screen_w
            sh = max(self.screen_h - 40, 100)
            img.thumbnail((sw, sh), Image.LANCZOS)
            station["photo"] = ImageTk.PhotoImage(img)
            station["last_update"] = datetime.now()
        except Exception as e:
            station["last_update"] = None   # keep old photo if exists

    def _show_current(self):
        station = self.stations[self.current_idx]
        if station["photo"]:
            self.img_label.configure(image=station["photo"])
            self.img_label.image = station["photo"]
        if station["last_update"]:
            ts = station["last_update"].strftime("%H:%M")
            text = f"{station['name']} · Updated at: {ts}"
        else:
            text = f"{station['name']} · Loading …"
        self.status.configure(text=text)

    def _switch(self):
        self.current_idx = (self.current_idx + 1) % len(self.stations)
        self._show_current()
        self.root.after(SWITCH_SEC * 1000, self._switch)

    def _start_refresh(self, delay_ms=REFRESH_SEC * 1000):
        self.root.after(delay_ms,
                        lambda: threading.Thread(target=self._refresh_all, daemon=True).start())

    def _refresh_all(self):
        for i in range(len(self.stations)):
            self._download_station(i)
        self.root.after(0, self._show_current)
        self._start_refresh()

    def _set_status(self, text):   # kept for compatibility
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()

    sx, sy, sw, sh = _screen_geometry(args.screen)

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.deiconify()
    root.update()
    TawesApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()