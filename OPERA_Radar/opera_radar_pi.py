"""
OPERA Radar – fullscreen animated display.
  Q / Escape  quit
  F           toggle fullscreen

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
"""

import threading
import tkinter as tk
from tkinter import ttk
from datetime import timezone
from PIL import Image, ImageTk
from opera_radar_functions import (
    OUTPUT_GIF, download_frames, download_single_frame,
    purge_old_cache, round_down_5min, save_animation
)
from datetime import datetime

REFRESH_SEC = 300
N_HOURS     = 2.0
FRAME_MS    = 200


class RadarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OPERA Radar")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())
        self.root.bind("f", lambda _: self.root.attributes("-fullscreen",
                                        not self.root.attributes("-fullscreen")))

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.pbar = ttk.Progressbar(self.root, orient="horizontal",
                                    mode="determinate", length=400)
        self.pbar.pack(side=tk.BOTTOM, pady=(0, 4))
        self.pbar.pack_forget()

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._raw    = []   # list of (datetime, PIL Image) — the sliding window
        self._frames = []   # list of (datetime, PhotoImage) for display
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
                # first run — download full window
                self._set_status("Downloading …")
                raw = download_frames(N_HOURS, progress_cb=self._set_progress)
                self.root.after(0, self.pbar.pack_forget)
            else:
                # incremental — fetch only the newest frame, drop the oldest
                now = round_down_5min(datetime.now(timezone.utc))
                self._set_status("Fetching latest frame …")
                new = download_single_frame(now)
                raw = (self._raw[1:] + [new]) if new else self._raw

            if not raw:
                self._set_status("No frames — retrying in 5 min")
            else:
                self._raw = raw
                save_animation(raw, OUTPUT_GIF, frame_ms=FRAME_MS)
                purge_old_cache()

                sw = self.root.winfo_screenwidth()
                sh = max(self.root.winfo_screenheight() - 60, 100)
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
        self._set_status(f"{len(tk_frames)} frames · {first}–{last} UTC · +{REFRESH_SEC // 60} min")
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
        self._tick()

    def _tick(self):
        if not self._frames:
            return
        dt, photo = self._frames[self._idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo  # prevent GC
        self._idx = (self._idx + 1) % len(self._frames)
        self._anim_id = self.root.after(FRAME_MS, self._tick)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    root = tk.Tk()
    RadarApp(root)
    root.mainloop()
