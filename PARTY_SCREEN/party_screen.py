#!/usr/bin/env python3
"""
Party screen: photos looping, messages fading, poll at bottom.
Pulls data from the come-inside backend.
"""

import argparse
import tkinter as tk
from PIL import Image, ImageTk
import requests
import io
import time
import threading

BACKEND = "http://192.168.0.103:8080"
REFRESH_MS = 3000
PHOTO_HOLD_MS = 6000

class PartyScreen:
    def __init__(self, root):
        self.root = root
        self.root.title("Party")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.state = {"shots": [], "notes": [], "polls": []}
        self.photo_idx = 0
        self.current_photo = None
        self.message_alpha = 0
        self.running = True

        self.update_loop()
        self.photo_loop()

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
            shot = shots[self.photo_idx % len(shots)]
            self.show_photo(shot)
            self.photo_idx += 1
        self.draw_overlay()
        self.root.after(PHOTO_HOLD_MS, self.photo_loop)

    def show_photo(self, shot):
        try:
            url = shot.get("src")
            if not url:
                return
            if url.startswith("/"):
                url = BACKEND + url
            r = requests.get(url, timeout=6)
            img = Image.open(io.BytesIO(r.content))
            # Fit to screen
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            img.thumbnail((sw, sh - 180), Image.Resampling.LANCZOS)
            self.current_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("photo")
            self.canvas.create_image(sw // 2, (sh - 180) // 2,
                                     image=self.current_photo, tags="photo")
        except Exception as e:
            print("photo error:", e)

    def draw_overlay(self):
        self.canvas.delete("overlay")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Latest message (top)
        notes = self.state.get("notes", [])
        if notes:
            text = notes[0].get("text", "")
            name = notes[0].get("name", "")
            msg = f"{text}  — {name}" if name else text
            self.canvas.create_text(sw // 2, 60, text=msg,
                                    fill="white", font=("Arial", 32, "bold"),
                                    tags="overlay", width=sw - 80)

        # Poll at bottom
        polls = self.state.get("polls", [])
        if polls:
            poll = polls[0]
            y = sh - 140
            self.canvas.create_text(sw // 2, y, text=poll.get("question", ""),
                                    fill="white", font=("Arial", 22), tags="overlay")
            total = sum(o.get("votes", 0) for o in poll.get("options", [])) or 1
            x = 80
            for opt in poll.get("options", []):
                pct = int(opt.get("votes", 0) / total * 100)
                label = f"{opt.get('label', '')}  {pct}%"
                self.canvas.create_text(x, y + 50, text=label,
                                        fill="white", font=("Arial", 18),
                                        tags="overlay", anchor="w")
                # simple bar
                bar_w = 200
                self.canvas.create_rectangle(x, y + 70, x + bar_w, y + 85,
                                             outline="white", tags="overlay")
                self.canvas.create_rectangle(x, y + 70, x + bar_w * pct / 100, y + 85,
                                             fill="white", tags="overlay")
                x += 280

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()

    root = tk.Tk()
    PartyScreen(root)
    root.mainloop()

if __name__ == "__main__":
    main()