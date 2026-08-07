"""
SPARTACUS 7-day climate anomaly – fullscreen dashboard for the Pi lockscreens.
  Q / Escape  quit
  R           force a refresh now

On every startup the 7 most recent *available* days of the SPARTACUS v3 1 km
grid (precipitation, sunshine duration, TM24, TN, TX) are downloaded for the
whole of Austria, averaged, and compared against the 1991–2020 normal for the
same calendar days.  While the app keeps running it checks again every few
hours, so a display left on for weeks does not go stale.

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
from pathlib import Path

from PIL import Image, ImageTk

from spartacus_data import build_report
from spartacus_plot import render

# ── config ───────────────────────────────────────────────────────────────────
CACHE_DIR     = Path(__file__).parent / "cache"
IMAGE_PATH    = CACHE_DIR / "spartacus_anomaly.png"
REFRESH_HOURS = 6                # re-check while running (the archive is daily)
RETRY_MIN     = 30               # minutes to wait after a failed update


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


class SpartacusApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._photo = None
        self._busy = False
        self._pending = None

        root.title("SPARTACUS 7-day anomaly")
        root.configure(bg="#0b0f16")
        root.bind("<Escape>", lambda _: root.quit())
        root.bind("q", lambda _: root.quit())
        root.bind("r", lambda _: self._kick_off())

        self.img_label = tk.Label(root, bg="#0b0f16", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(root, text="Starting…", bg="#0b0f16", fg="#8797ac",
                               font=("DejaVu Sans", 11))
        self.status.place(relx=0.5, rely=0.5, anchor="center")

        # Show the last render straight away so the screen is never blank,
        # then fetch the current data — every startup, no schedule.
        if IMAGE_PATH.exists():
            self._show(IMAGE_PATH)
        self._kick_off()

    # ── refreshing ───────────────────────────────────────────────────────────
    def _kick_off(self):
        """Fetch and render now; reschedules itself once finished."""
        if self._pending is not None:
            self.root.after_cancel(self._pending)
            self._pending = None
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        delay = RETRY_MIN * 60
        try:
            self._set_status("Downloading the last 7 available days and building the "
                             "1991–2020 climatology…\nThe first run takes a few minutes.")
            report = build_report()
            self._set_status("Rendering…")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            render(report, IMAGE_PATH, width=self.screen_w, height=self.screen_h)
            self.root.after(0, lambda: self._show(IMAGE_PATH))
            delay = REFRESH_HOURS * 3600
            print(f"[SPARTACUS] showing {report['dates'][0]} … {report['dates'][-1]} "
                  f"– next check in {REFRESH_HOURS} h", flush=True)
        except Exception as exc:
            print(f"[SPARTACUS] update failed: {exc}", flush=True)
            if not IMAGE_PATH.exists():
                self._set_status(f"Update failed: {exc}\nRetrying in {RETRY_MIN} min.")
        finally:
            self._busy = False
            self._pending = self.root.after(int(delay * 1000), self._kick_off)

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
