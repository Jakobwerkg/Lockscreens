"""
Foto-Webcam slideshow – cycles through multiple foto-webcam.eu cameras fullscreen.
  Q / Escape  quit
  Left / Right arrow  jump to previous / next camera
  --wifi-ssid NAME --wifi-pass PASS   auto-connect to WiFi on startup (optional)

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
"""

import argparse
import io
import platform
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from PIL import Image, ImageTk
import requests

# ── cameras to display ──────────────────────────────────────────────────────
WEBCAMS = [
    "heiligenblut",
    "innsbruck",
    "innsbruck-uni-west",
    "innsbruck-uni",
    "moesern",
    "kleinfleisskees",
    "braunschweigerhuette",
    "kuersingerhuette",
    "grossvenediger",
    "konkordiahuette",
    "zugspitze",
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


# ── WiFi auto-connect (nmcli) ───────────────────────────────────────────────

def _is_internet() -> bool:
    """Quick check: can we reach public DNS?"""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def _wait_for_internet(timeout_sec: int = 60) -> bool:
    for _ in range(timeout_sec):
        if _is_internet():
            return True
        time.sleep(1)
    return False


def ensure_wifi_connected(ssid: str | None, password: str | None):
    """If ssid given: connect via nmcli if needed. Otherwise just wait briefly for DHCP."""
    if not ssid:
        _wait_for_internet(25)  # allow normal boot DHCP
        return
    if _is_internet():
        return
    print(f"[WiFi] Connecting to '{ssid}' ...")
    try:
        subprocess.run(
            ["nmcli", "device", "wifi", "connect", ssid, "password", password],
            check=False, timeout=45, capture_output=True, text=True
        )
        if _wait_for_internet(90):
            print("[WiFi] Connected + internet OK.")
        else:
            print("[WiFi] WiFi up but internet not confirmed yet.")
    except FileNotFoundError:
        print("[WiFi] nmcli not installed. Configure WiFi once via desktop or raspi-config.")
    except Exception as e:
        print(f"[WiFi] Auto-connect failed: {e}")


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

        # cache: cam → (PIL Image, label str)
        self._raw:   dict[str, tuple[Image.Image, str]] = {}
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
            img, label = _fetch_image(cam)          # PIL image only (thread-safe)
            with self._lock:
                self._raw[cam] = (img, label)
            if self.webcams[self._idx] == cam:
                self.root.after(0, self._show_current)
        except Exception as e:
            if self.webcams[self._idx] == cam:
                self._set_status(f"Error ({cam}): {e}")

    def _schedule_refresh(self, cam: str):
        threading.Thread(target=self._fetch_and_cache, args=(cam,), daemon=True).start()
        self.root.after(REFRESH_SEC * 1000, lambda c=cam: self._schedule_refresh(c))

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
            entry = self._raw.get(cam)
        if entry:
            pil_img, label = entry
            # PhotoImage MUST be created in main thread (fixes silent exit + update bug)
            sw = self.screen_w
            sh = max(self.screen_h - 40, 100)
            iw, ih = pil_img.size
            scale = min(sw / iw, sh / ih)
            resized = pil_img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(resized)

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
    parser.add_argument("--wifi-ssid", default=None,
                        help="WiFi SSID for auto-connect on boot (optional)")
    parser.add_argument("--wifi-pass", default=None,
                        help="WiFi password (paired with --wifi-ssid)")
    args = parser.parse_args()

    SLIDE_SEC = args.slide

    ensure_wifi_connected(args.wifi_ssid, args.wifi_pass)

    root = tk.Tk()
    root.withdraw()
    sx, sy, sw, sh = _screen_geometry(args.screen, root)
    if platform.system() == "Darwin":
        # macOS: native fullscreen hides menu bar and dock
        root.attributes("-fullscreen", True)
    else:
        # Linux/X11: borderless window covering the target monitor
        root.overrideredirect(True)
        root.geometry(f"{sw}x{sh}+{sx}+{sy}")
    root.deiconify()
    root.update()
    FotoWebcamApp(root, screen_w=sw, screen_h=sh, webcams=args.webcams)
    root.mainloop()
