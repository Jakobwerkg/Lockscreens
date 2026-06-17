# OPERA Radar Animation

Displays the latest EUMETNET OPERA max-reflectivity radar composite as a fullscreen animated loop.  
Frames are fetched every **5 minutes** in 5-minute steps for the last 2 hours.  
Source: [eumetnet.eu/observations/opera-radar-animation](https://www.eumetnet.eu/observations/opera-radar-animation/)

---

## Files

| File | Description |
|---|---|
| `opera_radar_pi.py` | Main app — fullscreen display + auto-refresh |
| `opera_radar_functions.py` | Download, cache, and GIF-building logic |
| `install_pi.sh` | One-time dependency installer (Raspberry Pi) |
| `setup_autostart.sh` | Auto-launch on desktop login (Raspberry Pi) |
| `cache/` | Individual frames cached here (auto-purged after 6 h) |
| `opera_radar.gif` | Latest combined animation (overwritten every 5 min) |

---

## Mac

### Requirements

```bash
pip install pillow requests
```

Python's `tkinter` is included with the standard macOS Python installer from [python.org](https://www.python.org).  
If you installed Python via Homebrew and `tkinter` is missing:

```bash
brew install python-tk
```

### Run

```bash
cd OPERA_Radar
python3 opera_radar_pi.py
```

---

## Raspberry Pi

Tested on Raspberry Pi 5 with Raspberry Pi OS (Bookworm, 64-bit Desktop).

### 1 — Install dependencies

```bash
bash install_pi.sh
```

This runs:
```bash
sudo apt install python3-tk python3-pil python3-pil.imagetk python3-requests
pip3 install pillow requests
```

### 2 — Run

```bash
python3 opera_radar_pi.py
```

### 3 — Auto-start on boot (optional)

```bash
bash setup_autostart.sh
```

This creates `~/.config/autostart/opera-radar.desktop` so the display launches automatically when the desktop starts.

To remove auto-start:
```bash
rm ~/.config/autostart/opera-radar.desktop
```

---

## Controls

| Key | Action |
|---|---|
| `Q` or `Escape` | Quit |
| `F` | Toggle fullscreen |

---

## Configuration

Edit the constants at the top of `opera_radar_pi.py`:

| Variable | Default | Description |
|---|---|---|
| `REFRESH_SEC` | `300` | Seconds between data updates (5 min) |
| `N_HOURS` | `2.0` | Hours of history to display |
| `FRAME_MS` | `200` | Milliseconds per animation frame |

---

## Troubleshooting

**No window appears on Mac**  
Make sure you're using a Python build that includes Tk (python.org installer or `brew install python-tk`).

**`ModuleNotFoundError: No module named 'tkinter'` on Pi**  
```bash
sudo apt install python3-tk
```

**`ModuleNotFoundError: No module named 'PIL'`**  
```bash
pip3 install pillow
```

**All frames skipped / no data**  
The source server may be temporarily unavailable. The app retries automatically every 5 minutes.

**Display too small / wrong resolution on Pi**  
The app reads the screen resolution at startup via `winfo_screenwidth/height`. If running over SSH with X forwarding, set `DISPLAY=:0` before launching:
```bash
DISPLAY=:0 python3 opera_radar_pi.py
```
