"""
EUMETSAT VIS006 – fullscreen rolling 6-hour animation
Keeps last ~36 images in local cache (survives reboots)
Q / Escape = quit
"""

import argparse
import io
import platform
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk
import requests

URL = "https://eumetview.eumetsat.int/static-images/latestImages/EUMETSAT_MSG_VIS006_FullResolution.jpg"
CACHE_DIR = Path(__file__).parent / "cache"
REFRESH_MIN = 10          # download every 10 minutes
MAX_IMAGES = 36           # ~6 hours


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


def _load_cached_images():
    """Load existing images from cache (sorted by time)."""
    CACHE_DIR.mkdir(exist_ok=True)
    files = sorted(CACHE_DIR.glob("*.jpg"))[-MAX_IMAGES:]
    images = []
    for f in files:
        try:
            img = Image.open(f).convert("RGB")
            images.append((f.stem, img))
        except Exception:
            f.unlink(missing_ok=True)
    return images


def _download_latest():
    """Download current image and save with timestamp."""
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        r = requests.get(URL, timeout=30)
        r.raise_for_status()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        path = CACHE_DIR / f"{ts}.jpg"
        path.write_bytes(r.content)
        return path.stem, Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"[EUMETSAT] Download failed: {e}")
        return None, None


class EumetsatAnimApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.frames = []          # list of (timestamp_str, PhotoImage)
        self.idx = 0
        self.anim_id = None

        self.root.title("EUMETSAT VIS006")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        # Load existing cache (survives reboot)
        raw = _load_cached_images()
        for ts, pil in raw:
            self._add_frame(ts, pil)

        # Start periodic download + animation
        self._download_and_add()
        self.root.after(REFRESH_MIN * 60 * 1000, self._download_and_add)

        if self.frames:
            self._tick()
        else:
            self._set_status("Waiting for first images…")

    def _add_frame(self, ts: str, pil_img):
        sw = self.screen_w
        sh = max(self.screen_h - 40, 100)
        pil_img.thumbnail((sw, sh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(pil_img)
        self.frames.append((ts, photo))
        if len(self.frames) > MAX_IMAGES:
            self.frames.pop(0)

    def _download_and_add(self):
        ts, pil = _download_latest()
        if pil:
            self._add_frame(ts, pil)
            self._set_status(f"{len(self.frames)} images · last {ts}")
        self.root.after(REFRESH_MIN * 60 * 1000, self._download_and_add)

    def _tick(self):
        if not self.frames:
            return
        _, photo = self.frames[self.idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo
        self.idx = (self.idx + 1) % len(self.frames)
        self.anim_id = self.root.after(200, self._tick)   # ~5 fps

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
    EumetsatAnimApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()