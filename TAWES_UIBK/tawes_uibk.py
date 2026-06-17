"""
TAWES UIBK – fullscreen live image display, refreshes every 10 minutes.
  Q / Escape  quit
  F           toggle fullscreen

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
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

URL         = "https://ertel2.uibk.ac.at/ertel/data/pngs/lightningmaps/entrance.png"
REFRESH_SEC = 600  # 10 minutes


def _screen_geometry(index: int) -> tuple:
    """Return (x, y, w, h) for monitor *index* (sorted left-to-right)."""
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
        self.root     = root
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.root.title("TAWES UIBK")
        self.root.configure(bg="black")
        self.root.overrideredirect(True)  # borderless, stays on the screen set by geometry
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q",        lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._start_refresh(delay_ms=0)

    def _start_refresh(self, delay_ms=REFRESH_SEC * 1000):
        self.root.after(delay_ms,
                        lambda: threading.Thread(target=self._refresh, daemon=True).start())

    def _refresh(self):
        self._set_status("Fetching …")
        try:
            resp = requests.get(URL, timeout=15)
            resp.raise_for_status()

            sw = self.screen_w
            sh = max(self.screen_h - 40, 100)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img.thumbnail((sw, sh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            ts = datetime.now().strftime("%H:%M")

            def _show():
                self.img_label.configure(image=photo)
                self.img_label.image = photo
                self._set_status(f"Updated at: {ts}")

            self.root.after(0, _show)
        except Exception as e:
            self._set_status(f"Error: {e} — retrying in {REFRESH_SEC // 60} min")

        self._start_refresh()

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0,
                        help="Monitor index (0 = leftmost, 1 = next, …)")
    args = parser.parse_args()

    sx, sy, sw, sh = _screen_geometry(args.screen)

    root = tk.Tk()
    root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.update()  # let WM place the window before going fullscreen
    TawesApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()
