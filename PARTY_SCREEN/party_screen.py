#!/usr/bin/env python3
"""
Party screen: photo loop, fading messages, poll + drink counters at bottom.
"""

import argparse
import tkinter as tk
from PIL import Image, ImageTk
import requests
import io
import threading

BACKEND = "http://192.168.0.103:8080"
REFRESH_MS = 2000
PHOTO_HOLD_MS = 5000
MSG_SHOW_MS = 4000

DRINKS = [
    ("beer", "Bier"),
    ("wine", "Wein"),
    ("longdrink", "Longdrink"),
    ("shot", "Shot"),
    ("magenbitter", "Magenbitter"),
    ("bacardi", "Bacardi"),
    ("sozi", "SoZi"),
]

class PartyScreen:
    def __init__(self, root):
        self.root = root
        self.root.title("Party")
        self.root.configure(bg="#2b2118")
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.root.geometry("1440x900+1440+0")
        self.root.attributes("-fullscreen", True)

        self.canvas = tk.Canvas(root, bg="#2b2118", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.state = {"shots": [], "notes": [], "polls": [], "drinks": {}}
        self.photo_idx = 0
        self.msg_idx = 0
        self.current_photo = None
        self.running = True

        self.update_loop()
        self.photo_loop()
        self.message_loop()

    def fetch_state(self):
        try:
            r = requests.get(f"{BACKEND}/api/state", timeout=4)
            if r.ok:
                self.state = r.json()
        except Exception:
            pass

    def update_loop(self):
        if not self.running:
            return
        threading.Thread(target=self.fetch_state, daemon=True).start()
        self.root.after(REFRESH_MS, self.update_loop)

    def photo_loop(self):
        if not self.running:
            return
        shots = self.state.get("shots", [])
        if shots:
            self.show_photo(shots[self.photo_idx % len(shots)])
            self.photo_idx += 1
        self.draw_bottom()
        self.root.after(PHOTO_HOLD_MS, self.photo_loop)

    def show_photo(self, shot):
        try:
            url = shot.get("src")
            if not url:
                return
            if url.startswith("/"):
                url = BACKEND + url
            r = requests.get(url, timeout=6)
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            self.current_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("photo")
            self.canvas.create_image(720, 360, image=self.current_photo, tags="photo")
        except Exception:
            pass

    def message_loop(self):
        if not self.running:
            return
        notes = self.state.get("notes", [])
        self.canvas.delete("message")
        if notes:
            n = notes[self.msg_idx % len(notes)]
            text = n.get("text", "")
            name = n.get("name", "")
            msg = f"“{text}”" if text else ""
            if name:
                msg += f"  — {name}"
            self.canvas.create_text(720, 60, text=msg,
                                    fill="#f4e2c4", font=("Georgia", 24),
                                    tags="message", width=1100)
            self.msg_idx += 1
            self.root.after(MSG_SHOW_MS, lambda: self.canvas.delete("message"))
        self.root.after(MSG_SHOW_MS + 1200, self.message_loop)

    def draw_bottom(self):
        self.canvas.delete("bottom")

        # --- Poll ---
        polls = self.state.get("polls", [])
        if polls:
            poll = polls[0]
            self.canvas.create_text(720, 680, text=poll.get("question", ""),
                                    fill="#f4e2c4", font=("Georgia", 18), tags="bottom")
            options = poll.get("options", [])
            total = sum(int(o.get("votes", 0)) for o in options) or 1
            x = 200
            for opt in options:
                votes = int(opt.get("votes", 0))
                pct = int(votes / total * 100)
                self.canvas.create_text(x, 715,
                                        text=f"{opt.get('label','')}  {votes} ({pct}%)",
                                        fill="#f4e2c4", font=("Georgia", 14),
                                        tags="bottom", anchor="w")
                x += 400

        # --- Drinks counter ---
        drinks = self.state.get("drinks", {})
        y = 780
        x = 80
        for key, label in DRINKS:
            count = int(drinks.get(key, 0))
            self.canvas.create_text(x, y,
                                    text=f"{label}\n{count}",
                                    fill="#f4e2c4", font=("Georgia", 14),
                                    tags="bottom", justify="center")
            x += 190

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=1)
    args = parser.parse_args()
    root = tk.Tk()
    PartyScreen(root)
    root.mainloop()

if __name__ == "__main__":
    main()