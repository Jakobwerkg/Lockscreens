#!/usr/bin/env python3
"""
Meteociel Playlist GIF Animator
- Plays each GIF for exactly 4 full loops then switches
- Day = 06:00–21:00 local time, Night = rest
- Shows "Day mode" / "Night mode" in status
- Refreshes ALL active GIFs every 3 minutes
"""

import argparse
import platform
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk, ImageSequence
import requests

CACHE_DIR = Path(__file__).parent / "cache"

# ==================== YOUR PLAYLIST ====================
PLAYLIST = [
    {"url": "https://modeles20.meteociel.fr/satellite/animsatirmtgeu.gif", "name": "IR EU", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/foudreli/anim.gif", "name": "Lightning", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatwvmtgeu.gif", "name": "WV EU", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatvistruecolmtgeu.gif", "name": "TrueColor EU", "mode": "day"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatvismtgde.gif", "name": "TrueColour DE", "mode": "day"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatircolmtgalt.gif", "name": "IR Atlantic", "mode": "both"},
]
# =======================================================


def is_daytime() -> bool:
    hour = datetime.now().hour
    return 6 <= hour < 21


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


def download_gif(url: str, dest: Path) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        r = requests.get(url, timeout=90, stream=True, headers=headers)
        print(f"[sat] {url} → status={r.status_code}")
        sys.stdout.flush()
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        print(f"[sat] Saved {dest} ({dest.stat().st_size} bytes)")
        sys.stdout.flush()
        return True
    except Exception as e:
        print(f"[sat] Download failed {url}: {type(e).__name__}: {e}")
        sys.stdout.flush()
        return False


def load_gif_frames(gif_path: Path):
    if not gif_path.exists():
        return [], 200
    frames = []
    try:
        im = Image.open(gif_path)
        for frame in ImageSequence.Iterator(im):
            frames.append((ImageTk.PhotoImage(frame.convert("RGB")),
                           frame.info.get("duration", 120)))
    except Exception as e:
        print(f"[sat] GIF load error: {e}")
        return [], 200
    return frames, 120


class PlaylistApp:
    def __init__(self, root, screen_w, screen_h):
        self.root = root
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.playlist = PLAYLIST
        self.active = []
        self.current_idx = 0
        self.play_count = 0
        self.frames = []
        self.frame_idx = 0
        self.anim_after = None

        self.current_gif = CACHE_DIR / "current.gif"
        self.next_gif = CACHE_DIR / "next.gif"

        self.root.title("Meteociel Playlist")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)
        self.status = tk.Label(self.root, text="Starting…", bg="black",
                               fg="#aaaaaa", font=("DejaVu Sans Mono", 11))
        self.status.pack(side=tk.BOTTOM, pady=(2, 4))

        self._update_active_playlist(first=True)
        self._load_and_start_current()

        self.root.after(5 * 60 * 1000, self._periodic_check)
        self.root.after(3 * 60 * 1000, self._refresh_all_gifs)

    def _update_active_playlist(self, first=False):
        is_day = is_daytime()
        mode_str = "Day" if is_day else "Night"
        new_active = [p for p in self.playlist
                      if p["mode"] == "both" or
                      (is_day and p["mode"] == "day") or
                      (not is_day and p["mode"] == "night")]

        if not new_active:
            new_active = [p for p in self.playlist if p["mode"] == "both"]

        if new_active != self.active:
            self.active = new_active
            self.current_idx = 0
            self.play_count = 0
            if not first:
                self._load_and_start_current()
        self._update_status(mode_str)

    def _periodic_check(self):
        self._update_active_playlist()
        self.root.after(5 * 60 * 1000, self._periodic_check)

    def _refresh_all_gifs(self):
        """Refresh ALL active GIFs every 3 minutes."""
        if not self.active:
            self.root.after(3 * 60 * 1000, self._refresh_all_gifs)
            return

        def refresh_all():
            for i, item in enumerate(self.active):
                dest = self.current_gif if i == self.current_idx else self.next_gif
                download_gif(item["url"], dest)

            # If current GIF was refreshed, reload it
            new_frames, _ = load_gif_frames(self.current_gif)
            if new_frames:
                self.frames = new_frames
                self.frame_idx = 0
                self.play_count = 0
                self._cancel_anim()
                self._tick()
                self._update_status()

            self.root.after(3 * 60 * 1000, self._refresh_all_gifs)

        threading.Thread(target=refresh_all, daemon=True).start()

    def _load_and_start_current(self):
        if not self.active:
            self._set_status("No active animations")
            return

        item = self.active[self.current_idx]
        self._set_status(f"Loading {item['name']}...")

        download_ok = download_gif(item["url"], self.current_gif)
        if not self.current_gif.exists() or not download_ok:
            self._set_status(f"Download failed: {item['name']}")
            return

        self.frames, _ = load_gif_frames(self.current_gif)
        if not self.frames:
            self._set_status("GIF error")
            return

        self.frame_idx = 0
        self.play_count = 0
        self._cancel_anim()
        self._tick()

        threading.Thread(target=self._preload_next, daemon=True).start()
        self._update_status()

    def _preload_next(self):
        if len(self.active) < 2:
            return
        next_idx = (self.current_idx + 1) % len(self.active)
        next_item = self.active[next_idx]
        download_gif(next_item["url"], self.next_gif)

    def _tick(self):
        if not self.frames:
            return
        photo, delay = self.frames[self.frame_idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo
        self.frame_idx = (self.frame_idx + 1) % len(self.frames)

        if self.frame_idx == 0:
            self.play_count += 1
            if self.play_count >= 4:
                self._advance()
                return
        self.anim_after = self.root.after(delay, self._tick)

    def _advance(self):
        self.current_idx = (self.current_idx + 1) % len(self.active)
        self.play_count = 0
        if self.next_gif.exists():
            self.next_gif.replace(self.current_gif)
        self._load_and_start_current()

    def _update_status(self, mode_override=None):
        if not self.active:
            text = "No active animations"
        else:
            item = self.active[self.current_idx]
            mode = mode_override or ("Day" if is_daytime() else "Night")
            next_name = self.active[(self.current_idx + 1) % len(self.active)]["name"]
            text = f"{item['name']} ({self.play_count + 1}/4) · {mode} mode · next: {next_name}"
        self._set_status(text)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))

    def _cancel_anim(self):
        if self.anim_after:
            self.root.after_cancel(self.anim_after)
            self.anim_after = None


# ==================== Single GIF mode (for testing) ====================
class SingleGifApp:
    def __init__(self, root, screen_w, screen_h, gif_url, name):
        self.root = root
        self.gif_url = gif_url
        self.name = name
        self.gif_path = CACHE_DIR / "single.gif"
        self.frames = []
        self.frame_idx = 0

        self.root.title(name)
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q", lambda _: self.root.quit())

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)
        self.status = tk.Label(self.root, text="Loading…", bg="black",
                               fg="#aaaaaa", font=("DejaVu Sans Mono", 11))
        self.status.pack(side=tk.BOTTOM, pady=(2, 4))

        if download_gif(gif_url, self.gif_path):
            self.frames, _ = load_gif_frames(self.gif_path)
        if self.frames:
            self._tick()
            self._set_status(f"{name} · {len(self.frames)} frames")
        else:
            self._set_status("Failed to load GIF")

    def _tick(self):
        if not self.frames:
            return
        photo, delay = self.frames[self.frame_idx]
        self.img_label.configure(image=photo)
        self.img_label.image = photo
        self.frame_idx = (self.frame_idx + 1) % len(self.frames)
        self.root.after(delay, self._tick)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--product", choices=["ir-eu", "truecol-de", "viscol-eu"])
    group.add_argument("--gif-url")
    parser.add_argument("--name", default="Custom")
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

    if args.product or args.gif_url:
        if args.product:
            mapping = {
                "ir-eu": ("https://modeles20.meteociel.fr/satellite/animsatirmtgeu.gif", "IR EU"),
                "truecol-de": ("https://modeles20.meteociel.fr/satellite/animsatvistruecolmtgde.gif", "TrueColor DE"),
                "viscol-eu": ("https://modeles20.meteociel.fr/satellite/animsatviscolmtgeu.gif", "Vis Color EU"),
            }
            url, name = mapping[args.product]
        else:
            url, name = args.gif_url, args.name
        SingleGifApp(root, sw, sh, url, name)
    else:
        PlaylistApp(root, sw, sh)

    root.mainloop()