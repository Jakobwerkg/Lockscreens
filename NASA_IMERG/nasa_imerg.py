"""
NASA IMERG – fullscreen global precipitation display, refreshes every 30 minutes.
  Q / Escape  quit

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
"""

import argparse
import io
import platform
import re
import subprocess
import threading
import tkinter as tk
from datetime import datetime, timezone
from PIL import Image, ImageTk
import requests

URL         = "https://svs.gsfc.nasa.gov/vis/a000000/a004200/a004285/imergert_1080p.now.png"
REFRESH_SEC = 1800  # 30 minutes


def _screen_geometry(index: int, root: tk.Tk) -> tuple:
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
    return (index * root.winfo_screenwidth(), 0, root.winfo_screenwidth(), root.winfo_screenheight())


class ImergApp:
    def __init__(self, root, screen_w, screen_h):
        self.root     = root
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.root.title("NASA IMERG")
        self.root.configure(bg="black")
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
            resp = requests.get(URL, timeout=30)
            resp.raise_for_status()

            sw = self.screen_w
            sh = max(self.screen_h - 40, 100)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            iw, ih = img.size
            scale = min(sw / iw, sh / ih)
            img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")

            def _show():
                self.img_label.configure(image=photo)
                self.img_label.image = photo
                self._set_status(f"NASA IMERG Global Precipitation  ·  {ts}")

            self.root.after(0, _show)
        except Exception as e:
            self._set_status(f"Error: {e} — retrying in 30 min")

        self._start_refresh()

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0,
                        help="Monitor index (0 = leftmost, 1 = next, …)")
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()
    sx, sy, sw, sh = _screen_geometry(args.screen, root)
    if platform.system() == "Darwin":
        root.attributes("-fullscreen", True)
    else:
        root.overrideredirect(True)
        root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.deiconify()
    root.update()
    ImergApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()
