# TAWES UIBK

Fullscreen live display of the UIBK lightning/weather map.  
Image is fetched every **10 minutes** and displayed immediately.  
Source: `https://ertel2.uibk.ac.at/ertel/data/pngs/lightningmaps/entrance.png`

---

## Files

| File | Description |
|---|---|
| `tawes_uibk.py` | Main app — fullscreen display + auto-refresh |
| `install_pi.sh` | One-time dependency installer (Raspberry Pi) |
| `setup_autostart.sh` | Auto-launch on desktop login (Raspberry Pi) |

---

## Mac

### Requirements

```bash
pip install pillow requests
```

`tkinter` is included with the python.org macOS installer.  
If you installed Python via Homebrew and `tkinter` is missing:

```bash
brew install python-tk
```

### Run

```bash
cd TAWES_UIBK
python3 tawes_uibk.py
```

---

## Raspberry Pi

Tested on Raspberry Pi 5 with Raspberry Pi OS (Bookworm, 64-bit Desktop).

### 1 — Install dependencies

```bash
bash install_pi.sh
```

### 2 — Run

```bash
python3 tawes_uibk.py
```

### 3 — Auto-start on boot (optional)

```bash
bash setup_autostart.sh
```

To remove auto-start:

```bash
rm ~/.config/autostart/tawes-uibk.desktop
```

---

## Controls

| Key | Action |
|---|---|
| `Q` or `Escape` | Quit |
| `F` | Toggle fullscreen |

---

## Configuration

Edit the constants at the top of `tawes_uibk.py`:

| Variable | Default | Description |
|---|---|---|
| `URL` | UIBK map URL | Image source |
| `REFRESH_SEC` | `600` | Seconds between fetches (10 min) |

---

## Troubleshooting

**No window on Mac**  
Use the python.org installer or `brew install python-tk`.

**`ModuleNotFoundError: No module named 'tkinter'` on Pi**  
```bash
sudo apt install python3-tk
```

**`ModuleNotFoundError: No module named 'PIL'`**  
```bash
pip3 install pillow
```

**Image not updating / fetch error shown**  
The source server may be temporarily unavailable. The app retries automatically every 10 minutes.

**Running over SSH on Pi**  
```bash
DISPLAY=:0 python3 tawes_uibk.py
```
