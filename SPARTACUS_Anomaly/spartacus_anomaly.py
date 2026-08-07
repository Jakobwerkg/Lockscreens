"""
SPARTACUS 7-day climate anomaly – fullscreen dashboard for the Pi lockscreens.
  Q / Escape  quit
  R           force a refresh now

Every day at 06:00 local time the last 7 days of the SPARTACUS v3 1 km grid
(precipitation, sunshine duration, TM24, TN, TX) are downloaded for the whole
of Austria, averaged, and compared against the 1991–2020 normal for the same
calendar days.  The rendered dashboard stays on screen in between.

Requirements:
  sudo apt install python3-tk python3-pil python3-pil.imagetk \
                   python3-numpy python3-matplotlib python3-netcdf4 python3-requests
"""

import argparse
import platform
import re
import subprocess
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageTk

from spartacus_data import build_report
from spartacus_plot import render

# ── config ───────────────────────────────────────────────────────────────────
CACHE_DIR    = Path(__file__).parent / "cache"
IMAGE_PATH   = CACHE_DIR / "spartacus_anomaly.png"
REFRESH_HOUR = 6                 # local time of the daily update
RETRY_MIN    = 30                # minutes to wait after a failed update


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
    return (index * root.winfo_screenwidth(), 0,
            root.winfo_screenwidth(), root.winfo_screenheight())


def _seconds_until_next_run(now=None) -> float:
    now = now or datetime.now()
    nxt = now.replace(hour=REFRESH_HOUR, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def _image_is_current(path: Path, now=None) -> bool:
    """True if the PNG was rendered after the most recent 06:00."""
    if not path.exists():
        return False
    now = now or datetime.now()
    last_run = now.replace(hour=REFRESH_HOUR, minute=0, second=0, microsecond=0)
    if last_run > now:
        last_run -= timedelta(days=1)
    return datetime.fromtimestamp(path.stat().st_mtime) >= last_run


class SpartacusApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._photo = None
        self._busy = False

        root.title("SPARTACUS 7-day anomaly")
        root.configure(bg="#0b0f16")
        root.bind("<Escape>", lambda _: root.quit())
        root.bind("q", lambda _: root.quit())
        root.bind("r", lambda _: self._kick_off(force=True))

        self.img_label = tk.Label(root, bg="#0b0f16", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(root, text="Starting…", bg="#0b0f16", fg="#8797ac",
                               font=("DejaVu Sans", 11))
        self.status.place(relx=0.5, rely=0.5, anchor="center")

        # Show whatever is on disk immediately, then update if it is stale.
        if IMAGE_PATH.exists():
            self._show(IMAGE_PATH)
        self._kick_off()

    # ── scheduling ───────────────────────────────────────────────────────────
    def _kick_off(self, force=False):
        if self._busy:
            return
        if not force and _image_is_current(IMAGE_PATH):
            wait = _seconds_until_next_run()
            self._set_status(None)
            print(f"[SPARTACUS] up to date – next update in {wait / 3600:.1f} h", flush=True)
            self.root.after(int(wait * 1000) + 5000, self._kick_off)
            return
        self._busy = True
        threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        delay = RETRY_MIN * 60
        try:
            self._set_status("Downloading SPARTACUS grids and building the "
                             "1991–2020 climatology…\nThe first run takes a few minutes.")
            report = build_report()
            self._set_status("Rendering…")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            render(report, IMAGE_PATH, width=self.screen_w, height=self.screen_h)
            self.root.after(0, lambda: self._show(IMAGE_PATH))
            delay = _seconds_until_next_run()
            print(f"[SPARTACUS] updated – next update in {delay / 3600:.1f} h", flush=True)
        except Exception as exc:
            print(f"[SPARTACUS] update failed: {exc}", flush=True)
            delay = RETRY_MIN * 60
            if not IMAGE_PATH.exists():
                self._set_status(f"Update failed: {exc}\nRetrying in {RETRY_MIN} min.")
        finally:
            self._busy = False
            self.root.after(int(delay * 1000) + 5000, self._kick_off)

    # ── display ──────────────────────────────────────────────────────────────
    def _show(self, path: Path):
        try:
            img = Image.open(path).convert("RGB")
            if img.size != (self.screen_w, self.screen_h):
                img = img.resize((self.screen_w, self.screen_h), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.img_label.configure(image=self._photo)
            self.status.place_forget()
        except Exception as exc:
            self._set_status(f"Could not display image: {exc}")

    def _set_status(self, text):
        def apply():
            if text is None:
                self.status.place_forget()
            else:
                self.status.configure(text=text)
                self.status.lift()
                self.status.place(relx=0.5, rely=0.5, anchor="center")
        self.root.after(0, apply)


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

    SpartacusApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()
