# Lockscreens

Fullscreen live weather displays for Raspberry Pi, running across two screens.

---

## Screens at a glance

| Pi | SSH | Screen 0 | Screen 1 |
|---|---|---|---|
| **Pi2** | `ssh bildschirm2@192.168.0.172` | OPERA Radar | TAWES UIBK |
| **Pi1** | `ssh bildschirm1@192.168.0.236` | NASA IMERG | Foto-Webcam |

### Apps

| App | Source | Refresh |
|---|---|---|
| `OPERA_Radar` | EUMETNET OPERA max-reflectivity composite | 5 min |
| `TAWES_UIBK` | UIBK lightning/weather map | 10 min |
| `Foto_Webcam` | foto-webcam.eu – webcam slideshow (Heiligenblut, Innsbruck, …) | 5 min / 10 s slide |
| `NASA_IMERG` | NASA global precipitation (IMERG) | 30 min |
| `SPARTACUS_Anomaly` | GeoSphere SPARTACUS v3 – 7-day anomaly vs. 1991–2020 | on startup + 6 h |

`SPARTACUS_Anomaly` is not assigned to a screen yet — both Pis are full. Run it
on whichever screen you want to free up (see [SPARTACUS_Anomaly/README.md](SPARTACUS_Anomaly/README.md)).

---

## Daily workflow — edit on Mac, deploy to Pi

```bash
git add <files>
git commit -m "your message"
git push

# then on the Pi:
ssh bildschirm2@192.168.0.172
cd ~/Lockscreens && git pull
# restart the processes (see below)
```

Or use `deploy.sh` which does push + pull + restart in one step:

```bash
bash deploy.sh bildschirm2@192.168.0.172
bash deploy.sh bildschirm1@192.168.0.236
```

---

## Restarting apps on the Pi

After a `git pull`, kill the old processes and relaunch:

**Pi2** (`bildschirm2@192.168.0.172` — OPERA Radar + TAWES):
```bash
pkill -f opera_radar_pi.py; pkill -f tawes_uibk.py
DISPLAY=:0 python3 ~/Lockscreens/OPERA_Radar/opera_radar_pi.py --screen 0 &
DISPLAY=:0 python3 ~/Lockscreens/TAWES_UIBK/tawes_uibk.py --screen 1 &
```

**Pi1** (`bildschirm1@192.168.0.236` — NASA IMERG + Foto-Webcam):
```bash
pkill -f foto_webcam.py; pkill -f nasa_imerg.py
DISPLAY=:0 python3 ~/Lockscreens/NASA_IMERG/nasa_imerg.py --screen 0 &
DISPLAY=:0 python3 ~/Lockscreens/Foto_Webcam/foto_webcam.py --screen 1 &
```

Or just reboot the Pi — both apps start automatically via `~/.config/autostart/`.

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

# install dependencies
bash OPERA_Radar/install_pi.sh     # Pi2
bash TAWES_UIBK/install_pi.sh      # Pi2
bash Foto_Webcam/install_pi.sh     # Pi1
bash NASA_IMERG/install_pi.sh      # Pi1
bash SPARTACUS_Anomaly/install_pi.sh

# set up autostart
bash OPERA_Radar/setup_autostart.sh   # Pi2 – screen 0
bash TAWES_UIBK/setup_autostart.sh   # Pi2 – screen 1
bash NASA_IMERG/setup_autostart.sh   # Pi1 – screen 0
bash Foto_Webcam/setup_autostart.sh  # Pi1 – screen 1
bash SPARTACUS_Anomaly/setup_autostart.sh 0   # argument = monitor index
```

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
The source URL at `ertel2.uibk.ac.at` is temporarily unreachable — the app retries automatically every 10 minutes.

**SSH without password prompts**
```bash
ssh-copy-id bildschirm2@192.168.0.172
ssh-copy-id bildschirm1@192.168.0.236
```

---

## Files

```
Lockscreens/
  deploy.sh              ← push + pull + restart on Pi
  setup_pi.sh            ← run once on Pi after cloning
  OPERA_Radar/           → Pi2, screen 0
  TAWES_UIBK/            → Pi2, screen 1
  NASA_IMERG/            → Pi1, screen 0
  Foto_Webcam/           → Pi1, screen 1
  SPARTACUS_Anomaly/     → not assigned to a screen yet
```
