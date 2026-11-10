#!/usr/bin/env python3
"""Party screen for the display Pi.

Reads http://<host>:8080/api/display and draws it itself.
Photos are shown whole above the drink bars. A new comment appears in the side space, drifts down, then fades.
Drink counts race as horizontal bars along the bottom.

    python3 party_screen.py
    python3 party_screen.py --backend http://192.168.0.103:8080
"""

import argparse
import io
import queue
import sys
import threading
import tkinter as tk
from PIL import Image, ImageTk
import requests

BACKEND = "http://192.168.0.103:8080"
REFRESH_MS = 2000
PHOTO_HOLD_MS = 5000
TICK_MS = 40
FALL_PX_PER_SEC = 28

BG = (0x2B, 0x21, 0x18)
CREAM = (0xF4, 0xE2, 0xC4)
RUST = "#d4532b"
INK = "#1a120c"
TRACK = "#3a2e24"
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

DRINK_LABELS = (
    ("beer", "Bier"),
    ("wine", "Wein"),
    ("longdrink", "Longdrink"),
    ("shot", "Shot"),
    ("magenbitter", "Magenbitter"),
    ("bacardi", "Bacardi Cola"),
    ("sozi", "SoZi"),
)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return "#{:02x}{:02x}{:02x}".format(
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def fit_size(img, width, height):
    width = max(1, int(width))
    height = max(1, int(height))
    scale = min(width / img.width, height / img.height)
    return max(1, int(img.width * scale)), max(1, int(img.height * scale))


def normalize(data):
    if not isinstance(data, dict):
        return {"photos": [], "messages": [], "drinks": []}
    if "photos" in data or "messages" in data:
        return {
            "photos": data.get("photos") or [],
            "messages": data.get("messages") or [],
            "drinks": data.get("drinks") or [],
        }
    photos = []
    for shot in data.get("shots") or []:
        photos.append(
            {
                "id": shot.get("id"),
                "url": shot.get("url") or shot.get("src") or "",
                "caption": shot.get("caption") or "",
                "at": shot.get("at") or 0,
            }
        )
    raw = data.get("drinks") or {}
    drinks = []
    if isinstance(raw, dict):
        for key, label in DRINK_LABELS:
            value = raw.get(key, 0)
            if isinstance(value, dict):
                continue
            try:
                count = int(value or 0)
            except (TypeError, ValueError):
                count = 0
            drinks.append({"id": key, "label": label, "count": count})
    else:
        drinks = raw
    return {"photos": photos, "messages": data.get("notes") or [], "drinks": drinks}


class PartyScreen:
    def __init__(self, root, backend):
        self.root.title("Geburtstagsfeschtl")
        self.root.configure(bg="#2b2118")
        self.root.bind("<Escape>", lambda e: self.shutdown())

        # True fullscreen, no top bar
        self.root.overrideredirect(True)
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        if sys.platform == "win32":
            self.root.geometry("{0}x{1}+0+0".format(self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
        else:
            self.root.geometry("1440x900+1440+0")

        self.canvas = tk.Canvas(root, bg="#2b2118", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.session = requests.Session()
        self.session.trust_env = False
        self.inbox = queue.Queue()

        self.photos = []
        self.drinks = []
        self.photo_idx = 0
        self.seen = None
        self.floaters = []
        self.bar_shown = {}
        self.band_top = 10**9
        self.current_photo = None
        self.last_image = None
        self.photo_rect = None
        self.painted_key = None
        self.photo_token = 0
        self.status = "Verbinde mit " + self.backend + " …"
        self.running = True

        self.root.bind("<Configure>", lambda e: self.paint_current())
        self.poll()
        self.photo_loop()
        self.tick()

    def size(self):
        self.canvas.update_idletasks()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
        return w, h

    def shutdown(self):
        self.running = False
        self.root.destroy()

    def poll(self):
        if not self.running:
            return
        threading.Thread(target=self.fetch, daemon=True).start()
        self.root.after(REFRESH_MS, self.poll)

    def fetch(self):
        errors = []
        for path in ("/api/display", "/api/state"):
            try:
                res = self.session.get(self.backend + path, timeout=4)
                if res.ok:
                    self.inbox.put(("data", normalize(res.json())))
                    return
                errors.append(path + " " + str(res.status_code))
            except Exception as exc:
                errors.append(path + " " + str(exc))
        message = "Kommt nicht ran: " + self.backend + " (" + "; ".join(errors) + ")"
        print(message, flush=True)
        self.inbox.put(("error", message))

    def drain(self):
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                return
            if kind == "error":
                if not self.drinks and self.last_image is None:
                    self.status = payload
            elif kind == "photo":
                img, token = payload
                if token == self.photo_token:
                    self.last_image = img
                    self.status = ""
                    self.paint_current()
            elif kind == "data":
                self.apply(payload)

    def apply(self, data):
        had_photos = bool(self.photos)
        self.photos = data.get("photos") or []
        self.drinks = data.get("drinks") or []
        self.status = ""
        messages = data.get("messages") or []
        ids = [m.get("id") for m in messages]
        if self.seen is None:
            self.seen = set(ids)
        else:
            fresh = [
                m
                for m in reversed(messages)
                if m.get("id") not in self.seen and (m.get("text") or "").strip()
            ]
            for i, message in enumerate(fresh):
                self.seen.add(message.get("id"))
                self.spawn(message, i * 78)
        if self.photos and (not had_photos or self.last_image is None):
            self.photo_idx = 0
            self.request_photo(self.photos[0])

    def photo_loop(self):
        if not self.running:
            return
        if self.photos:
            shot = self.photos[self.photo_idx % len(self.photos)]
            self.photo_idx += 1
            self.request_photo(shot)
        self.root.after(PHOTO_HOLD_MS, self.photo_loop)

    def request_photo(self, shot):
        self.photo_token += 1
        threading.Thread(target=self.load_photo, args=(shot, self.photo_token), daemon=True).start()

    def load_photo(self, shot, token):
        url = shot.get("url") or shot.get("src") or ""
        if not url:
            return
        if url.startswith("/"):
            url = self.backend + url
        try:
            res = self.session.get(url, timeout=8)
            res.raise_for_status()
            img = Image.open(io.BytesIO(res.content)).convert("RGB")
        except Exception as exc:
            print("Foto fehlgeschlagen:", url, exc, flush=True)
            self.inbox.put(("error", "Foto nicht geladen: " + url))
            return
        self.inbox.put(("photo", (img, token)))

    def paint_current(self):
        if self.last_image is None:
            return
        try:
            w, h = self.size()
            area_h = max(1, min(self.band_top, h))
            nw, nh = fit_size(self.last_image, w, area_h)
            x = (w - nw) // 2
            y = max(0, (area_h - nh) // 2)
            key = (id(self.last_image), nw, nh, x, y)
            if key == self.painted_key:
                return
            framed = self.last_image.resize((nw, nh), Image.LANCZOS)
            self.current_photo = ImageTk.PhotoImage(framed)
            self.painted_key = key
            self.photo_rect = (x, y, nw, nh)
            self.canvas.delete("photo")
            self.canvas.create_image(x, y, image=self.current_photo, anchor="nw", tags="photo")
            self.canvas.tag_lower("photo")
        except tk.TclError:
            return

    def gutters(self, w):
        pad = 28
        rect = self.photo_rect
        if rect:
            left_edge, _y, pw, _ph = rect
            right_edge = left_edge + pw
        else:
            left_edge = int(w * 0.24)
            right_edge = w - left_edge
        return {
            "left_x": pad,
            "left_w": max(0, left_edge - pad * 2),
            "right_x": w - pad,
            "right_w": max(0, w - right_edge - pad * 2),
            "bottom": max(80, self.band_top - 12),
        }

    def spawn(self, message, drop):
        text = (message.get("text") or "").strip()
        name = (message.get("name") or "").strip()
        line = text if not name else text + "\n— " + name
        w, _h = self.size()
        g = self.gutters(w)
        y = 36 + drop
        left = self.canvas.create_text(
            g["left_x"], y, text=line, anchor="nw", fill="#f4e2c4",
            font=(FONT, 22), width=max(80, g["left_w"]), tags="message", justify="left",
        )
        right = self.canvas.create_text(
            g["right_x"], y, text=line, anchor="ne", fill="#f4e2c4",
            font=(FONT, 22), width=max(80, g["right_w"]), tags="message", justify="right",
        )
        self.floaters.append({"left": left, "right": right, "y": y, "born": y, "text": line})

    def tick(self):
        if not self.running:
            return
        try:
            self.drain()
            self.animate()
        except Exception as exc:
            self.status = str(exc)
            print("screen:", exc, flush=True)
        if self.running:
            self.root.after(TICK_MS, self.tick)

    def animate(self):
        step = FALL_PX_PER_SEC * TICK_MS / 1000
        w, h = self.size()
        self.draw_bars(w, h)
        self.paint_current()
        g = self.gutters(w)
        font_size = 22 if min(g["left_w"], g["right_w"]) >= 220 else 16
        alive = []
        for floater in self.floaters:
            floater["y"] += step
            travel = floater["y"] - floater["born"]
            fade = 1.0
            if travel > 180:
                fade = max(0.0, 1 - (travel - 180) / 280)
            color = mix(BG, CREAM, fade)
            gone = fade <= 0.04 or floater["y"] >= g["bottom"]
            if gone:
                self.canvas.delete(floater["left"])
                self.canvas.delete(floater["right"])
                continue
            if g["left_w"] < 70:
                self.canvas.itemconfig(floater["left"], state="hidden")
                self.canvas.itemconfig(floater["right"], state="hidden")
                alive.append(floater)
                continue
            self.canvas.itemconfig(floater["left"], state="normal")
            self.canvas.itemconfig(floater["right"], state="normal")
            self.canvas.coords(floater["left"], g["left_x"], floater["y"])
            self.canvas.coords(floater["right"], g["right_x"], floater["y"])
            self.canvas.itemconfig(
                floater["left"], fill=color, width=g["left_w"], font=(FONT, font_size),
            )
            self.canvas.itemconfig(
                floater["right"], fill=color, width=g["right_w"], font=(FONT, font_size),
            )
            alive.append(floater)
        self.floaters = alive
        self.draw_status(w, h)
        self.canvas.tag_raise("message")
        self.canvas.tag_raise("bottom")
        self.canvas.tag_raise("status")

    def draw_status(self, w, h):
        self.canvas.delete("status")
        if not self.status:
            return
        self.canvas.create_text(
            w // 2, h // 2, text=self.status, fill="#f4e2c4",
            font=(FONT, 22), width=w - 120, tags="status", justify="center",
        )

    def draw_bars(self, w, h):
        self.canvas.delete("bottom")
        drinks = self.drinks
        if not drinks:
            self.band_top = h
            return
        row_h = 28
        band_h = 16 + len(drinks) * row_h
        top = h - band_h
        self.band_top = top
        self.canvas.create_rectangle(0, top, w, h, fill=INK, outline="", tags="bottom")
        highest = max((int(d.get("count") or 0) for d in drinks), default=0)
        bar_x = 210
        bar_w = max(40, w - bar_x - 80)
        y = top + 14
        for drink in drinks:
            key = drink.get("id") or drink.get("label")
            count = int(drink.get("count") or 0)
            target = 0 if highest == 0 else count / highest
            shown = self.bar_shown.get(key, target)
            shown += (target - shown) * 0.12
            self.bar_shown[key] = shown
            label = drink.get("label") or key
            self.canvas.create_text(
                24, y, text=label, anchor="w", fill="#f4e2c4",
                font=(FONT, 14, "bold"), tags="bottom",
            )
            self.canvas.create_rectangle(
                bar_x, y - 7, bar_x + bar_w, y + 7, fill=TRACK, outline="", tags="bottom",
            )
            if shown > 0.01:
                fill = RUST if count == highest and count > 0 else "#f4e2c4"
                self.canvas.create_rectangle(
                    bar_x, y - 7, bar_x + max(8, int(bar_w * shown)), y + 7,
                    fill=fill, outline="", tags="bottom",
                )
            self.canvas.create_text(
                bar_x + bar_w + 12, y, text=str(count), anchor="w", fill="#f4e2c4",
                font=(FONT, 14, "bold"), tags="bottom",
            )
            y += row_h


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=BACKEND)
    parser.add_argument("--screen", type=int, default=1)
    args = parser.parse_args()
    root = tk.Tk()
    PartyScreen(root, args.backend)
    root.mainloop()


if __name__ == "__main__":
    main()
