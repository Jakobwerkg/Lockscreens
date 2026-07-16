#!/usr/bin/env python3
"""
Meteociel Playlist GIF Animator
- Plays each GIF for exactly 4 full loops then switches
- Day = 06:00–21:00 local time, Night = rest
- Shows "Day mode" / "Night mode" in status
- Refreshes ALL active GIFs every 3 minutes
- Ends with latest MODIS still image (20 s) then loops
"""

import argparse
import platform
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk, ImageSequence
import requests

CACHE_DIR = Path(__file__).parent / "cache"

# ==================== YOUR PLAYLIST ====================
PLAYLIST = [
    {"url": "https://modeles20.meteociel.fr/satellite/animsatirmtgeu.gif",
     "name": "IR EU", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/foudreli/anim.gif",
     "name": "Lightning", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatwvmtgeu.gif",
     "name": "WV EU", "mode": "both"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatvistruecolmtgeu.gif",
     "name": "TrueColor EU", "mode": "day"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatvismtgde.gif",
     "name": "TrueColour DE", "mode": "day"},
    {"url": "https://modeles20.meteociel.fr/satellite/animsatircolmtgalt.gif",
     "name": "IR Atlantic", "mode": "both"},
    # Still image at the end (latest of the 3 MODIS satellites)
    {"type": "still", "name": "MODIS Latest", "mode": "both", "duration": 20},
]
# =======================================================

MODIS_CANDIDATES = [
    "https://neige.meteociel.fr/satellite/modis/terrade.jpg",
    "https://neige.meteociel.fr/satellite/modis/aquade.jpg",
    "https://neige.meteociel.fr/satellite/modis/noaa21de.jpg",
]


def is_daytime() -> bool:
    hour = datetime.now().hour
    return 6 <= hour < 21


def get_latest_modis_url() -> str | None:
    """Return the URL of the most recently updated MODIS image among the 3 candidates.
    Prefers HTTP Last-Modified header. Falls back to the first working URL.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    best_url = None
    best_ts = -1.0
    working = []

    for url in MODIS_CANDIDATES:
        try:
            r = requests.head(url, timeout=15, headers=headers, allow_redirects=True)
            if r.status_code != 200:
                continue
            working.append(url)
            lm = r.headers.get("Last-Modified")
            if lm:
                try:
                    ts = parsedate_to_datetime(lm).timestamp()
                    if ts > best_ts:
                        best_ts = ts
                        best_url = url
                except Exception:
                    pass
        except Exception as e:
            print(f"[sat] HEAD failed {url}: {e}")
            sys.stdout.flush()
            continue

    if best_url:
        print(f"[sat] Latest MODIS by Last-Modified: {best_url}")
        sys.stdout.flush()
        return best_url

    # Fallback: any working one (prefer last in list = NOAA21 which was newest in examples)
    if working:
        print(f"[sat] No Last-Modified, falling back to {working[-1]}")
        sys.stdout.flush()
        return working[-1]
    return None


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
        self.still_after = None

        self.current_gif = CACHE_DIR / "current.gif"
        self.next_gif = CACHE_DIR / "next.gif"
        self.still_jpg = CACHE_DIR / "still.jpg"

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
        """Refresh ALL active GIFs every 3 minutes (skip stills)."""
        if not self.active:
            self.root.after(3 * 60 * 1000, self._refresh_all_gifs)
            return

        def refresh_all():
            for i, item in enumerate(self.active):
                if item.get("type") == "still":
                    continue
                dest = self.current_gif if i == self.current_idx else self.next_gif
                download_gif(item["url"], dest)

            # Reload current if it is a GIF
            if self.active and self.active[self.current_idx].get("type") != "still":
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

        # Special case: still image
        if item.get("type") == "still":
            self._show_still(item)
            return

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

    def _show_still(self, item):
        """Download the latest of the 3 MODIS images and display it for duration seconds."""
        self._cancel_anim()
        self._set_status(f"Loading {item['name']}...")

        url = get_latest_modis_url()
        if not url:
            self._set_status("No MODIS image available")
            # skip to next after short delay
            self.still_after = self.root.after(5000, self._advance)
            return

        ok = download_gif(url, self.still_jpg)
        if not ok or not self.still_jpg.exists():
            self._set_status(f"Download failed: {item['name']}")
            self.still_after = self.root.after(5000, self._advance)
            return

        try:
            pil = Image.open(self.still_jpg).convert("RGB")
            # Fit to screen while keeping aspect
            sw, sh = self.screen_w, max(self.screen_h - 40, 100)
            pil.thumbnail((sw, sh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(pil)
            self.img_label.configure(image=photo)
            self.img_label.image = photo
            self.frames = []          # no animation
            duration_ms = int(item.get("duration", 20) * 1000)
            self._update_status()
            self.still_after = self.root.after(duration_ms, self._advance)
            print(f"[sat] Showing still {url} for {item.get('duration', 20)}s")
            sys.stdout.flush()
        except Exception as e:
            print(f"[sat] Still load error: {e}")
            sys.stdout.flush()
            self._set_status("Still error")
            self.still_after = self.root.after(5000, self._advance)

    def _preload_next(self):
        if len(self.active) < 2:
            return
        next_idx = (self.current_idx + 1) % len(self.active)
        next_item = self.active[next_idx]
        if next_item.get("type") == "still":
            return
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
        if self.next_gif.exists() and self.active[self.current_idx].get("type") != "still":
            try:
                self.next_gif.replace(self.current_gif)
            except Exception:
                pass
        self._load_and_start_current()

    def _update_status(self, mode_override=None):
        if not self.active:
            text = "No active animations"
        else:
            item = self.active[self.current_idx]
            mode = mode_override or ("Day" if is_daytime() else "Night")
            next_name = self.active[(self.current_idx + 1) % len(self.active)]["name"]
            if item.get("type") == "still":
                text = f"{item['name']} (still) · {mode} mode · next: {next_name}"
            else:
                text = f"{item['name']} ({self.play_count + 1}/4) · {mode} mode · next: {next_name}"
        self._set_status(text)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))

    def _cancel_anim(self):
        if self.anim_after:
            self.root.after_cancel(self.anim_after)
            self.anim_after = None
        if self.still_after:
            self.root.after_cancel(self.still_after)
            self.still_after = None


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
