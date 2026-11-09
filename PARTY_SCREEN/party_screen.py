#!/usr/bin/env python3
import argparse
import tkinter as tk
from PIL import Image, ImageTk
import requests
import io
import threading
import sys

BACKEND = "http://192.168.0.103:8080"
REFRESH_MS = 3000
PHOTO_HOLD_MS = 6000

class PartyScreen:
    def __init__(self, root):
        self.root = root
        self.root.title("Party")
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        # Right screen (HDMI-A-2)
        self.root.geometry("1440x900+1440+0")
        self.root.attributes("-fullscreen", True)
        self.root.lift()
        self.root.attributes("-topmost", True)

        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.state = {"shots": [], "notes": [], "polls": []}
        self.photo_idx = 0
        self.current_photo = None
        self.running = True

        self.update_loop()
        self.photo_loop()

    def fetch_state(self):
        try:
            r = requests.get(f"{BACKEND}/api/state", timeout=4)
            if r.ok:
                self.state = r.json()
                print(f"state ok: {len(self.state.get('shots',[]))} photos", file=sys.stderr, flush=True)
        except Exception as e:
            print("fetch error:", e, file=sys.stderr, flush=True)

    def update_loop(self):
        if not self.running: return
        threading.Thread(target=self.fetch_state, daemon=True).start()
        self.root.after(REFRESH_MS, self.update_loop)

    def photo_loop(self):
        if not self.running: return
        shots = self.state.get("shots", [])
        if shots:
            self.show_photo(shots[self.photo_idx % len(shots)])
            self.photo_idx += 1
        self.draw_overlay()
        self.root.after(PHOTO_HOLD_MS, self.photo_loop)

    def show_photo(self, shot):
        try:
            url = shot.get("src")
            if not url: return
            if url.startswith("/"): url = BACKEND + url
            r = requests.get(url, timeout=6)
            img = Image.open(io.BytesIO(r.content))
            sw, sh = 1440, 900
            img.thumbnail((sw, sh - 200), Image.Resampling.LANCZOS)
            self.current_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("photo")
            self.canvas.create_image(sw//2, (sh-200)//2, image=self.current_photo, tags="photo")
        except Exception as e:
            print("photo error:", e, file=sys.stderr, flush=True)

    def draw_overlay(self):
        self.canvas.delete("overlay")
        notes = self.state.get("notes", [])
        if notes:
            msg = notes[0].get("text", "")
            self.canvas.create_text(720, 40, text=msg, fill="white",
                                    font=("Arial", 26, "bold"), tags="overlay", width=1300)
        polls = self.state.get("polls", [])
        if polls:
            p = polls[0]
            self.canvas.create_text(720, 820, text=p.get("question", ""),
                                    fill="white", font=("Arial", 20), tags="overlay")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=1)
    args = parser.parse_args()
    root = tk.Tk()
    PartyScreen(root)
    root.mainloop()

if __name__ == "__main__":
    main()