"""
OPERA Radar – fullscreen animated display.
  Q / Escape  quit
  F           toggle fullscreen

  Now uses up to ~100 frames (last ~8.5 hours) and always advances
  to the most recent available frame on each refresh.

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
"""

import argparse
import os
import re
import subprocess
import sys
import threading
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tkinter import ttk
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageTk
from opera_radar_functions import (
    OUTPUT_GIF, download_frames, download_single_frame,
    purge_old_cache, round_down_5min, save_animation
)

REFRESH_SEC = 300
N_HOURS     = 8.5   # ~100 frames (5-min radar)
FRAME_MS    = 200


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


class RadarApp:
    def __init__(self, root, screen_w, screen_h):
        self.root     = root
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.root.title("OPERA Radar")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.pbar = ttk.Progressbar(self.root, orient="horizontal",
                                    mode="determinate", length=400)
        self.pbar.pack(side=tk.BOTTOM, pady=(0, 4))
        self.pbar.pack_forget()

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._raw    = []
        self._frames = []
        self._idx    = 0
        self._anim_id = None

        self._start_refresh(delay_ms=0)

    def _start_refresh(self, delay_ms=REFRESH_SEC * 1000):
        self.root.after(delay_ms,
                        lambda: threading.Thread(target=self._refresh, daemon=True).start())

    def _set_progress(self, current, total):
        def _u():
            if current == 1:
                self.pbar.configure(maximum=total, value=0)
                self.pbar.pack(side=tk.BOTTOM, pady=(0, 4))
            self.pbar.configure(value=current)
            self.status.configure(text=f"Downloading  {current}/{total}")
        self.root.after(0, _u)

    def _refresh(self):
        try:
            if not self._raw:
                self._set_status("Downloading …")
                raw = download_frames(N_HOURS, progress_cb=self._set_progress)
                self.root.after(0, self.pbar.pack_forget)
            else:
                # --- FIX: always try to pull the most recent available frames ---
                self._set_status("Fetching latest frames …")
                now = round_down_5min(datetime.now(timezone.utc))
                new_frames = []
                # Check up to last 6 slots (30 min) so we catch the real latest
                # even if the exact current 5-min slot has no image yet on server
                for i in range(6):
                    dt = now - timedelta(minutes=5 * i)
                    if self._raw and dt <= self._raw[-1][0]:
                        break
                    f = download_single_frame(dt)
                    if f:
                        new_frames.append(f)
                if new_frames:
                    # merge + deduplicate by timestamp, keep only the newest N_HOURS worth
                    combined = self._raw + new_frames
                    seen = {}
                    for dt, img in combined:
                        seen[dt] = img
                    max_frames = int(N_HOURS * 12) + 1
                    raw = sorted(seen.items())[-max_frames:]
                else:
                    raw = self._raw

            if not raw:
                self._set_status("No frames — retrying in 5 min")
            else:
                self._raw = raw
                save_animation(raw, OUTPUT_GIF, frame_ms=FRAME_MS)
                purge_old_cache(keep_hours=12)

                sw = self.screen_w
                sh = max(self.screen_h - 60, 100)
                tk_frames = []
                for dt, img in raw:
                    resized = img.convert("RGB")
                    resized.thumbnail((sw, sh), Image.LANCZOS)
                    tk_frames.append((dt, ImageTk.PhotoImage(resized)))

                self.root.after(0, lambda: self._load(tk_frames))
        except Exception as e:
            self.root.after(0, self.pbar.pack_forget)
            self._set_status(f"Error: {e}")

        self._start_refresh()

    def _load(self, tk_frames):
        self._frames = tk_frames
        self._idx = 0
        first = tk_frames[0][0].strftime("%H:%M")
        last  = tk_frames[-1][0].strftime("%H:%M")
        ts    = datetime.now().strftime("%H:%M")
        self._set_status(f"{len(tk_frames)} frames · {first}–{last} UTC · Updated at: {ts}")
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
        self._tick()

    def _tick(self):
        if not self._frames:
            return
        dt, photo = self._frames[self._idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo
        self._idx = (self._idx + 1) % len(self._frames)
        self._anim_id = self.root.after(FRAME_MS, self._tick)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0,
                        help="Monitor index (0 = leftmost, 1 = next, …)")
    args = parser.parse_args()

    sx, sy, sw, sh = _screen_geometry(args.screen)

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.deiconify()
    root.update()
    RadarApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()
