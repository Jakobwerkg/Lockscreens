# Lockscreens

Fullscreen live weather displays for Raspberry Pi.

| App | Source | Refresh |
|---|---|---|
| `OPERA_Radar` | EUMETNET OPERA max-reflectivity composite | 5 min |
| `TAWES_UIBK` | UIBK lightning/weather map | 10 min |

---

## Workflow

### First time — Mac

```bash
cd /Users/jakobwerkgarner/code/Lockscreens
git init
git add .
git commit -m "initial commit"
gh repo create Lockscreens --private --source=. --push
```

### First time — Pi

```bash
# SSH into the Pi
ssh pi@raspberrypi.local

# Clone and set up
git clone https://github.com/jakobwerkgarner/Lockscreens.git ~/Lockscreens
cd ~/Lockscreens
bash setup_pi.sh

# Enable the display you want (only one at a time — both are fullscreen)
systemctl --user enable --now opera-radar
# or
systemctl --user enable --now tawes-uibk
```

### Daily — edit on Mac, deploy to Pi

```bash
# make your changes, then:
git add .
git commit -m "your message"
bash deploy.sh pi@raspberrypi.local
```

`deploy.sh` pushes to GitHub, SSHes to the Pi, pulls the latest code, and restarts the running service automatically.

---

## Service commands (on the Pi)

```bash
# status
systemctl --user status opera-radar
systemctl --user status tawes-uibk

# start / stop / restart
systemctl --user start opera-radar
systemctl --user stop opera-radar
systemctl --user restart opera-radar

# logs
journalctl --user -u opera-radar -f

# switch display (stop one, start the other)
systemctl --user stop opera-radar
systemctl --user start tawes-uibk
```

---

## Files

```
Lockscreens/
  deploy.sh          ← run on Mac to push + deploy to Pi
  setup_pi.sh        ← run once on Pi after cloning
  .gitignore
  OPERA_Radar/
    opera_radar_pi.py
    opera_radar_functions.py
    install_pi.sh
    README.md
  TAWES_UIBK/
    tawes_uibk.py
    install_pi.sh
    README.md
```

---

## Requirements

**Mac**
```bash
pip install pillow requests
brew install python-tk  # only if installed via Homebrew
```

**Pi** — handled by `setup_pi.sh` / `install_pi.sh`.

---

## Troubleshooting

**Service starts but no window appears on Pi**  
Make sure the Pi boots to desktop with auto-login enabled:
`sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin

**Running over SSH (no desktop)**  
```bash
DISPLAY=:0 python3 OPERA_Radar/opera_radar_pi.py
```

**`deploy.sh` asks for a password every time**  
Set up SSH key auth:
```bash
ssh-copy-id pi@raspberrypi.local
```
