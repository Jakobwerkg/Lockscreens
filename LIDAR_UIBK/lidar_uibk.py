"""
LIDAR UIBK – fullscreen live PNG display
Updates every ~5-10 min when new image is available.
Q / Escape = quit
"""
import io
import argparse
import platform
import re
import subprocess
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageTk
import requests

URL = "https://ertel2.uibk.ac.at/ertel/data/pngs/lidar142_current.png"
REFRESH_SEC = 300          # check every 5 min


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


class LidarApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.current_photo = None
        self.last_etag = None

        self.root.title("LIDAR UIBK")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._refresh()
        self.root.after(REFRESH_SEC * 1000, self._refresh)

    def _refresh(self):
        try:
            headers = {}
            if self.last_etag:
                headers["If-None-Match"] = self.last_etag

            r = requests.get(URL, headers=headers, timeout=20)
            if r.status_code == 304:
                self._set_status(f"Up to date · {datetime.now().strftime('%H:%M')}")
            elif r.status_code == 200:
                self.last_etag = r.headers.get("ETag")
                img = Image.open(io.BytesIO(r.content)).convert("RGB")

                # fit to screen
                sw, sh = self.screen_w, max(self.screen_h - 40, 100)
                img.thumbnail((sw, sh), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)

                self.img_label.configure(image=photo)
                self.img_label.image = photo
                self.current_photo = photo

                self._set_status(f"Updated {datetime.now().strftime('%H:%M')}")
            else:
                self._set_status(f"HTTP {r.status_code}")
        except Exception as e:
            self._set_status(f"Error: {e}")

        self.root.after(REFRESH_SEC * 1000, self._refresh)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
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
    LidarApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()