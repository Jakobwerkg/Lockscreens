"""
NASA IMERG 7-day animation – fullscreen looping video from official SVS MP4.
  Q / Escape  quit

Fetches the official 1920x1080 MP4 (~342 frames) and extracts frames with ffmpeg.
Always shows the most recent available animation (checks server every 6 h).

Requirements:
  pip install requests pillow
  sudo apt install python3-tk ffmpeg  (Raspberry Pi)
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageTk
import requests

# ── config ───────────────────────────────────────────────────────────────────
MP4_URL      = "https://svs.gsfc.nasa.gov/vis/a000000/a004200/a004285/imergert_1080p_30.mp4"
CACHE_DIR    = Path(__file__).parent / "cache" / "imerg"
MP4_PATH     = CACHE_DIR / "imergert_1080p_30.mp4"
FRAMES_DIR   = CACHE_DIR / "frames"
REFRESH_SEC  = 6 * 3600          # check for newer MP4 every 6 hours
FRAME_DELAY  = 50                # ms per frame (~20 fps – feels fluid)
MAX_AGE_HOURS = 6


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


def _is_file_recent(path: Path, hours: int) -> bool:
    if not path.exists():
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return age < timedelta(hours=hours)


def ensure_latest_animation(progress_cb=None):
    """Download MP4 (if newer) + extract frames with ffmpeg. Idempotent and efficient."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    need_download = True

    # 1. Check server Last-Modified (lightweight HEAD)
    try:
        head = requests.head(MP4_URL, timeout=15, allow_redirects=True)
        if head.status_code == 200:
            server_lm = head.headers.get("Last-Modified")
            if server_lm and MP4_PATH.exists():
                # very rough age check; if we have a recent file we skip
                if _is_file_recent(MP4_PATH, MAX_AGE_HOURS):
                    need_download = False
    except Exception:
        pass  # network issue → use whatever we have on disk

    # 2. Download if needed
    if need_download or not MP4_PATH.exists():
        print("[IMERG] Downloading latest MP4 ...")
        try:
            with requests.get(MP4_URL, stream=True, timeout=60) as r:
                r.raise_for_status()
                MP4_PATH.write_bytes(b"")  # touch
                with open(MP4_PATH, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
            print(f"[IMERG] MP4 saved ({MP4_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
        except Exception as e:
            print(f"[IMERG] Download failed: {e}")
            if not MP4_PATH.exists():
                return False

    # 3. Extract frames if frames dir is empty or MP4 is newer than frames
    frame_files = sorted(FRAMES_DIR.glob("*.png"))
    mp4_mtime = MP4_PATH.stat().st_mtime if MP4_PATH.exists() else 0
    frames_need_update = len(frame_files) == 0 or any(
        f.stat().st_mtime < mp4_mtime for f in frame_files[:5]
    )

    if frames_need_update:
        print("[IMERG] Extracting frames with ffmpeg (this may take a minute on first run)...")
        # Clean old frames
        for f in FRAMES_DIR.glob("*.png"):
            f.unlink(missing_ok=True)

        # Extract at native quality (one PNG per video frame)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(MP4_PATH),
            "-vf", "scale=1920:1080",   # keep max resolution
            str(FRAMES_DIR / "%04d.png")
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"[IMERG] Extracted {len(list(FRAMES_DIR.glob('*.png')))} frames")
        except subprocess.CalledProcessError as e:
            print(f"[IMERG] ffmpeg failed: {e.stderr}")
            return False

    return True


class ImergVideoApp:
    def __init__(self, root, screen_w, screen_h):
        self.root     = root
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._frames  = []   # list of PhotoImage
        self._idx     = 0
        self._anim_id = None

        self.root.title("NASA IMERG 7-day")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q",        lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading 7-day IMERG animation…", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._start_refresh(delay_ms=0)

    def _start_refresh(self, delay_ms=REFRESH_SEC * 1000):
        self.root.after(delay_ms,
                        lambda: threading.Thread(target=self._refresh, daemon=True).start())

    def _refresh(self):
        self._set_status("Checking for latest IMERG animation…")
        ok = ensure_latest_animation()
        if not ok:
            self._set_status("Failed to load animation – retrying later")
            self._start_refresh()
            return

        # Load / reload all frames (resized to screen)
        self._set_status("Loading frames into memory…")
        frame_files = sorted(FRAMES_DIR.glob("*.png"))
        if not frame_files:
            self._set_status("No frames found")
            self._start_refresh()
            return

        tk_frames = []
        for path in frame_files:
            try:
                img = Image.open(path).convert("RGB")
                img.thumbnail((self.screen_w, max(self.screen_h - 60, 100)), Image.LANCZOS)
                tk_frames.append(ImageTk.PhotoImage(img))
            except Exception:
                continue

        if not tk_frames:
            self._set_status("Could not load any frames")
            self._start_refresh()
            return

        self.root.after(0, lambda: self._load_animation(tk_frames))
        self._start_refresh()

    def _load_animation(self, tk_frames):
        self._frames = tk_frames
        self._idx = 0
        n = len(tk_frames)
        ts = datetime.now().strftime("%H:%M")
        self._set_status(f"IMERG 7-day loop · {n} frames · Updated {ts}")
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
        self._tick()

    def _tick(self):
        if not self._frames:
            return
        photo = self._frames[self._idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo
        self._idx = (self._idx + 1) % len(self._frames)
        self._anim_id = self.root.after(FRAME_DELAY, self._tick)

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

    ImergVideoApp(root, screen_w=sw, screen_h=sh)
    root.mainloop()
