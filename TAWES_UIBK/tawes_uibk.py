"""
TAWES UIBK – fullscreen live image display, refreshes every 10 minutes.
  Q / Escape  quit
  F           toggle fullscreen

Requirements:
  pip install requests pillow
  sudo apt install python3-tk  (Raspberry Pi)
"""

import io
import threading
import tkinter as tk
from PIL import Image, ImageTk
import requests

URL         = "https://ertel2.uibk.ac.at/ertel/data/pngs/lightningmaps/entrance.png"
REFRESH_SEC = 600  # 10 minutes


class TawesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TAWES UIBK")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda _: self.root.quit())
        self.root.bind("q",        lambda _: self.root.quit())
        self.root.bind("f", lambda _: self.root.attributes("-fullscreen",
                                        not self.root.attributes("-fullscreen")))

        self.img_label = tk.Label(self.root, bg="black", bd=0)
        self.img_label.pack(expand=True, fill=tk.BOTH)

        self.status = tk.Label(self.root, text="Loading …", bg="black",
                               fg="#cccccc", font=("DejaVu Sans Mono", 12))
        self.status.pack(side=tk.BOTTOM, pady=(4, 2))

        self._start_refresh(delay_ms=0)

    def _start_refresh(self, delay_ms=REFRESH_SEC * 1000):
        self.root.after(delay_ms,
                        lambda: threading.Thread(target=self._refresh, daemon=True).start())

    def _refresh(self):
        self._set_status("Fetching …")
        try:
            resp = requests.get(URL, timeout=15)
            resp.raise_for_status()

            sw = self.root.winfo_screenwidth()
            sh = max(self.root.winfo_screenheight() - 40, 100)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img.thumbnail((sw, sh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            def _show():
                self.img_label.configure(image=photo)
                self.img_label.image = photo  # prevent GC
                self._set_status(f"Updated · +{REFRESH_SEC // 60} min")

            self.root.after(0, _show)
        except Exception as e:
            self._set_status(f"Error: {e} — retrying in {REFRESH_SEC // 60} min")

        self._start_refresh()

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    root = tk.Tk()
    TawesApp(root)
    root.mainloop()
