# Lockscreens

Fullscreen live weather displays for Raspberry Pi.

Maintained by Jakob Werkgarner and Stefan Müller.

---

### Apps

| App | Source | Refresh |
|---|---|---|
| `OPERA_Radar` | EUMETNET OPERA max-reflectivity composite | 5 min |
| `TAWES_UIBK` | UIBK lightning/weather map | 10 min |
| `Foto_Webcam` | foto-webcam.eu – webcam slideshow (Heiligenblut, Innsbruck, …) | 5 min / 10 s slide |
| `NASA_IMERG` | NASA global precipitation (IMERG) | 30 min |
| `SPARTACUS_Anomaly` | GeoSphere SPARTACUS v3 – 7-day anomaly vs. 1991–2020 | on startup + 6 h |

Each app is standalone — run any subset of them, on any Pi, on any screen. Nothing
in this repo assumes a fixed layout.

---

## Daily workflow — edit on Mac, deploy to Pi

```bash
git add <files>
git commit -m "your message"
git push

# then on the Pi:
ssh <user>@<pi-host>
cd ~/Lockscreens && git pull
# restart whichever apps are running on this Pi (see below)
```

Or use `deploy.sh` which does push + pull + restart in one step:

```bash
bash deploy.sh <user>@<pi-host>
```

---

## Restarting an app on the Pi

After a `git pull`, kill and relaunch whichever app(s) run on that Pi:

```bash
pkill -f <app_script>.py
DISPLAY=:0 python3 ~/Lockscreens/<App_Folder>/<app_script>.py --screen <N> &
```

e.g.
```bash
pkill -f opera_radar_pi.py
DISPLAY=:0 python3 ~/Lockscreens/OPERA_Radar/opera_radar_pi.py --screen 0 &
```

Or just reboot the Pi — apps set up with `setup_autostart.sh` start automatically
via `~/.config/autostart/`.

---

## First-time setup

### Mac

```bash
git clone https://github.com/Jakobwerkg/Lockscreens.git
cd Lockscreens
```

### Pi (run once after cloning)

```bash
git clone https://github.com/Jakobwerkg/Lockscreens.git ~/Lockscreens
cd ~/Lockscreens

# install dependencies for whichever app(s) you want on this Pi
bash <App_Folder>/install_pi.sh

# set up autostart
bash <App_Folder>/setup_autostart.sh
```

> Note: `SPARTACUS_Anomaly/setup_autostart.sh` takes the target screen index as
> an argument (`bash SPARTACUS_Anomaly/setup_autostart.sh 0`). The other apps'
> autostart scripts currently launch on a fixed screen — open the script and
> change the `--screen` value if you want it on a different one.

---

## Troubleshooting

**No window appears after reboot**
Make sure the Pi boots to desktop with auto-login:
`sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin

**Running manually over SSH**
```bash
DISPLAY=:0 python3 ~/Lockscreens/OPERA_Radar/opera_radar_pi.py --screen 0
```

**TAWES shows "Error: … retrying"**
The upstream source is temporarily unreachable — the app retries automatically every 10 minutes.

**SSH without password prompts**
```bash
ssh-copy-id <user>@<pi-host>
```

---

## Files

```
Lockscreens/
  deploy.sh              ← push + pull + restart on Pi
  setup_pi.sh            ← run once on Pi after cloning
  OPERA_Radar/
  TAWES_UIBK/
  NASA_IMERG/
  Foto_Webcam/
  SPARTACUS_Anomaly/
```
