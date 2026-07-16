"""
LIDAR UIBK + HATPRO – fullscreen live PNG display
Switches every 60 s between images.
Updates (ETag check) every 300 s.
Q / Escape = quit
"""
import io
import argparse
import platform
import re
import subprocess
import tkinter as tk
from datetime import datetime
from PIL import Image, ImageTk
import requests

LIDAR_URL = "https://ertel2.uibk.ac.at/ertel/data/pngs/lidar142_current.png"
HATPRO_URL = "https://ertel2.uibk.ac.at/ertel/data/pngs/hatpro/hatpro_current.png"
REFRESH_SEC = 300
SWITCH_SEC = 60


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

        self.images = [
            {"url": LIDAR_URL, "name": "LIDAR", "etag": None, "photo": None, "last_update": None},
            {"url": HATPRO_URL, "name": "HATPRO", "etag": None, "photo": None, "last_update": None},
        ]
        self.current_idx = 0

        self.root.title("LIDAR + HATPRO")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._initial_load()
        self.root.after(SWITCH_SEC * 1000, self._switch_image)
        self.root.after(REFRESH_SEC * 1000, self._refresh_all)

    def _initial_load(self):
        for i in range(len(self.images)):
            self._fetch_image(i, force=True)
        self._display_current()

    def _fetch_image(self, idx, force=False):
        img = self.images[idx]
        headers = {}
        if not force and img["etag"]:
            headers["If-None-Match"] = img["etag"]
        try:
            r = requests.get(img["url"], headers=headers, timeout=20)
            if r.status_code == 304:
                img["last_update"] = datetime.now()
            elif r.status_code == 200:
                img["etag"] = r.headers.get("ETag")
                pil = Image.open(io.BytesIO(r.content)).convert("RGB")
                sw, sh = self.screen_w, max(self.screen_h - 40, 100)
                pil.thumbnail((sw, sh), Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil)
                img["photo"] = photo
                img["last_update"] = datetime.now()
        except Exception:
            pass

    def _display_current(self):
        img = self.images[self.current_idx]
        if img["photo"]:
            self.img_label.configure(image=img["photo"])
            self.img_label.image = img["photo"]
        self._update_status()

    def _update_status(self):
        img = self.images[self.current_idx]
        if img["last_update"]:
            t = img["last_update"].strftime("%H:%M")
            text = f"{img['name']} · Updated {t}"
        else:
            text = f"{img['name']} · Loading …"
        self.status.configure(text=text)

    def _switch_image(self):
        self.current_idx = (self.current_idx + 1) % len(self.images)
        self._display_current()
        self.root.after(SWITCH_SEC * 1000, self._switch_image)

    def _refresh_all(self):
        for i in range(len(self.images)):
            self._fetch_image(i, force=False)
        self._display_current()
        self.root.after(REFRESH_SEC * 1000, self._refresh_all)


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
