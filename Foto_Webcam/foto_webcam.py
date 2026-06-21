"""
Foto-Webcam slideshow – cycles through multiple foto-webcam.eu cameras fullscreen.
  Q / Escape  quit
  Left / Right arrow  jump to previous / next camera

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
from datetime import datetime, timezone
from PIL import Image, ImageTk
import requests

# ── cameras to display ──────────────────────────────────────────────────────
WEBCAMS = [
    "heiligenblut",
    "innsbruck-uni-west",
    "innsbruck-uni",
    "kleinfleisskees",
]

SLIDE_SEC   = 10    # seconds between automatic slides
REFRESH_SEC = 300   # re-fetch each camera every 5 minutes


# ── helpers ─────────────────────────────────────────────────────────────────

def _screen_geometry(index: int, root: tk.Tk) -> tuple:
    # Linux/X11: use xrandr for multi-monitor support
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
    # macOS / fallback: use tkinter's own screen dimensions
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    return (index * sw, 0, sw, sh)


def _fetch_image(cam: str) -> tuple[Image.Image, str]:
    """Download the current image for *cam* via the /current/1200.jpg endpoint."""
    url  = f"https://www.foto-webcam.eu/webcam/{cam}/current/1200.jpg"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    img   = Image.open(io.BytesIO(resp.content)).convert("RGB")
    label = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")
    return img, label


# ── app ──────────────────────────────────────────────────────────────────────

class FotoWebcamApp:
    def __init__(self, root, screen_w, screen_h, webcams):
        self.root     = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.webcams  = webcams

        self.root.title("Foto-Webcam")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q",        lambda _: self.root.quit())
        self.root.bind("<Right>",  lambda _: self._jump(+1))
        self.root.bind("<Left>",   lambda _: self._jump(-1))

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(
            self.root, text="Loading …", bg="black",
            fg="#cccccc", font=("DejaVu Sans Mono", 12),
        )
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        # cache: cam → (PIL Image, label str)  and  cam → (PhotoImage, label str)
        self._raw:   dict[str, tuple[Image.Image, str]] = {}
        self._photos: dict[str, tuple[ImageTk.PhotoImage, str]] = {}
        self._lock  = threading.Lock()

        self._idx      = 0
        self._slide_id = None

        # initial parallel fetch, then start refresh loop for each cam
        for cam in self.webcams:
            threading.Thread(target=self._fetch_and_cache, args=(cam,), daemon=True).start()
            self.root.after(REFRESH_SEC * 1000,
                            lambda c=cam: self._schedule_refresh(c))

        self._advance_slide()

    # ── fetching ─────────────────────────────────────────────────────────────

    def _fetch_and_cache(self, cam: str):
        try:
            img, label = _fetch_image(cam)
            sw = self.screen_w
            sh = max(self.screen_h - 40, 100)
            img.thumbnail((sw, sh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            with self._lock:
                self._photos[cam] = (photo, label)
            # if this is the currently displayed cam, refresh it immediately
            if self.webcams[self._idx] == cam:
                self.root.after(0, self._show_current)
        except Exception as e:
            # leave stale image in place; update status only if currently shown
            if self.webcams[self._idx] == cam:
                self._set_status(f"Error ({cam}): {e}")

    def _schedule_refresh(self, cam: str):
        threading.Thread(target=self._fetch_and_cache, args=(cam,), daemon=True).start()
        self.root.after(REFRESH_SEC * 1000, lambda: self._schedule_refresh(cam))

    # ── slideshow ────────────────────────────────────────────────────────────

    def _advance_slide(self):
        self._show_current()
        self._slide_id = self.root.after(SLIDE_SEC * 1000, self._next_slide)

    def _next_slide(self):
        self._idx = (self._idx + 1) % len(self.webcams)
        self._advance_slide()

    def _jump(self, direction: int):
        if self._slide_id:
            self.root.after_cancel(self._slide_id)
        self._idx = (self._idx + direction) % len(self.webcams)
        self._advance_slide()

    def _show_current(self):
        cam = self.webcams[self._idx]
        n   = len(self.webcams)
        with self._lock:
            entry = self._photos.get(cam)
        if entry:
            photo, label = entry
            self.img_label.configure(image=photo)
            self.img_label.image = photo
            self._set_status(
                f"[{self._idx + 1}/{n}]  {cam}  ·  {label}"
                f"  ·  updated {datetime.now().strftime('%H:%M')}"
            )
        else:
            self._set_status(f"[{self._idx + 1}/{n}]  {cam}  ·  loading …")

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen",  type=int, default=0,
                        help="Monitor index (0 = leftmost, 1 = next, …)")
    parser.add_argument("--webcams", nargs="+", default=WEBCAMS,
                        metavar="NAME",
                        help="foto-webcam.eu camera slugs to display")
    parser.add_argument("--slide",   type=int, default=SLIDE_SEC,
                        help="Seconds between slides (default 10)")
    args = parser.parse_args()

    SLIDE_SEC = args.slide

    root = tk.Tk()
    root.withdraw()
    sx, sy, sw, sh = _screen_geometry(args.screen, root)
    root.overrideredirect(True)
    root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.deiconify()
    root.update()
    FotoWebcamApp(root, screen_w=sw, screen_h=sh, webcams=args.webcams)
    root.mainloop()
