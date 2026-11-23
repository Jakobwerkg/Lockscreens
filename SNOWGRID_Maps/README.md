# SNOWGRID snow depth maps

Downloads the latest **GeoSphere Austria SNOWGRID-CL v2.1** snow depth (daily,
1 km, all of Austria) and renders two display-ready PNG maps on a Raspberry Pi
4. It runs unattended from a systemd timer and can show the maps fullscreen
with `feh`.

| File | Shows |
|---|---|
| `output/snow_depth.png` | Snow depth [cm] on the latest day. Classes 0, 1, 5, 10, 20, 50, 100, 200+ cm. Cells without snow are transparent. |
| `output/snow_change_24h.png` | 24 h change [cm] = latest day − previous day. Diverging scale centred on 0, fixed at ±30 cm with arrows beyond. Cells with no snow on either day are transparent. |
| `output/archive/*_YYYY-MM-DD.png` | Dated copies of both, kept for 7 days |

Data: [GeoSphere Austria – SNOWGRID-CL v2.1](https://dataset.api.hub.geosphere.at/v1/grid/historical/snowgrid_cl-v2-1d-1km/metadata), CC BY 4.0.

---

## How it works

Each run (`python -m snowgrid.main --once`):

1. Reads the dataset metadata. Its `end_time` is the **latest day**. The model
   runs a few days behind, so the code never assumes "today".
2. If `cache/snowgrid_<latest>.nc` already exists, skips the download.
   Otherwise it requests `snow_depth` for *latest − 1* and *latest* in **one**
   NetCDF request over the full metadata `bbox`. That is 2 × 329 × 584 =
   384 272 values, well under the API's 10 M-value NetCDF limit. One run makes
   at most two requests, against the limits of 5/s and 240/h.
3. Loads only that parameter and those two time steps as float32, then
   converts m → cm.
4. Renders both maps on the native EPSG:3416 grid. `ccrs.epsg(3416)` is both
   the projection and the transform, so the raster is not reprojected. Draws
   borders, Bundesländer, major rivers, lakes and city labels from offline
   Natural Earth 1:10 m data.
5. Writes each PNG to a temp file and then `rename`s it into place, so `feh`
   never shows a half-written image. Both maps are swapped in together.
6. Deletes cache files and dated PNGs older than 7 days.

If the published images already show the latest day (with the same config),
the run stops after step 1. Any failure (network, API, bad data) is logged and
leaves the last good images untouched.

### Layout

```
SNOWGRID_Maps/
  config.toml                  all settings
  requirements.txt
  install.sh / uninstall.sh
  snowgrid/
    config.py                  load + validate config.toml
    fetch.py                   metadata, download (retry/backoff), cache, NetCDF reading
    plot.py                    the two maps, atomic PNG writing
    naturalearth.py            offline Natural Earth data (prefetched by install.sh)
    main.py                    CLI
  systemd/
    snowgrid.service           oneshot run (system unit, runs as your user)
    snowgrid.timer             at boot + every 3 h, Persistent=true
    snowgrid-display.service   optional feh slideshow (user unit, X11)
  output/  cache/  naturalearth/  .venv/     created by install.sh / at runtime
```

---

## Install

Requirements: Raspberry Pi 4 with **Raspberry Pi OS (64-bit, Bookworm or
newer)**, Python ≥ 3.11 and network access. For the display you also need the
desktop with auto-login on **X11**.

```bash
git clone https://github.com/Jakobwerkg/Lockscreens.git ~/Lockscreens   # if not cloned yet
cd ~/Lockscreens/SNOWGRID_Maps
./install.sh
```

Run it as your normal user, not root; it calls `sudo` where needed.
`install.sh`:

1. Installs apt packages: `python3-venv`, `python3-pip`, and `feh` if the
   display is enabled.
2. Creates `.venv` and installs `requirements.txt`. On **aarch64** pip uses
   prebuilt wheels. On other architectures (32-bit OS, x86) it installs
   `python3-cartopy` and the other Python libraries from apt and creates the
   venv with `--system-site-packages`.
3. Downloads all Natural Earth layers into `naturalearth/`, so rendering
   needs no network.
4. Installs `snowgrid.service` and `snowgrid.timer` into
   `/etc/systemd/system/`, then does **one test run** and prints the log.
5. Enables the timer and, if `[display] enabled = true`, installs and starts
   `snowgrid-display.service` as a user unit.

It is safe to re-run. Re-run it after changing `[schedule]`, `[display]` or
any path in `config.toml`. Other settings take effect on the next run.

**X11 vs. Wayland:** current Raspberry Pi OS images default to Wayland. To
switch to X11, run `sudo raspi-config` → *Advanced Options* → *Wayland* → *X11*,
then reboot. (`feh` usually also runs under XWayland, but the display unit is
written for X11: it waits for `/tmp/.X11-unix/X0`.) To stop the screen going blank: `sudo raspi-config` → *Display Options*
→ *Screen Blanking* → *No*.

### Uninstall

```bash
./uninstall.sh              # units, venv, Natural Earth data, cache, images
./uninstall.sh --keep-data  # ... but keep output/ and cache/
```

---

## Manual test

```bash
cd ~/Lockscreens/SNOWGRID_Maps
.venv/bin/python -m snowgrid.main --once            # normal run (skips if up to date)
.venv/bin/python -m snowgrid.main --once --force    # ignore cache: download + render again
.venv/bin/python -m snowgrid.main --date 2026-02-15 # a specific day (UTC)
.venv/bin/python -m snowgrid.main --once -v         # debug logging (tracebacks on errors)
.venv/bin/python -m snowgrid.main --config /path/to/other.toml --once
```

Without `--once`, it loops and runs every `interval_hours`. That's useful
without systemd; the timer uses `--once`.

`--date` always writes the dated copies to `output/archive/`. It replaces
`snow_depth.png` / `snow_change_24h.png` only if the day is the latest
available, so the display always shows the newest data.

The same run through systemd, exactly as the timer does it:

```bash
sudo systemctl start snowgrid.service    # blocks until the run is finished
```

A good run logs something like:

```
dataset available 1961-01-01 … 2026-11-21 (EPSG:3416, unit m)
downloading snow_depth for 2026-11-20 and 2026-11-21
saved snowgrid_2026-11-21.nc (523.7 kB, 384272 values, 1.6 s)
2026-11-21: max depth 331.0 cm, snow cover 23.0 %, 24 h change -4.0 … +4.0 cm, 83888 valid cells
published snow_depth.png, snow_change_24h.png
```

Sanity check: Austria is about 83 900 km², so about 83 900 valid 1 km cells.
Everything else (outside Austria) is NaN and drawn transparent.

## Check the timer

```bash
systemctl list-timers snowgrid.timer      # next / last run
systemctl status snowgrid.timer
systemctl status snowgrid.service         # result of the last run
```

The timer fires 1 min after boot (the service waits for
`network-online.target`), then at 00:00, 03:00, 06:00 … (plus up to 5 min of
random delay). `Persistent=true` catches up on a run missed while the Pi was
off.

## Logs

Everything goes to stdout, so to journald:

```bash
journalctl -u snowgrid                    # all runs
journalctl -u snowgrid -e                 # jump to the end
journalctl -u snowgrid --since today
journalctl -u snowgrid -f                 # follow live
journalctl --user -u snowgrid-display     # the feh slideshow
```

## Display

```bash
systemctl --user status snowgrid-display
systemctl --user restart snowgrid-display
systemctl --user disable --now snowgrid-display   # or set [display] enabled = false and re-run install.sh
```

`feh` shows both maps on one monitor, switches every 30 s, and re-reads the
files every 60 s, so new maps appear without restarting. The unit waits for
the X server and for the first images. It restarts on failure.

### Choosing the monitor

`[display] screen` picks the monitor the same way `--screen N` does in the
other apps: 0 = leftmost, 1 = the next one to the right (from `xrandr`). The
window is placed exactly over that monitor. After changing it:

```bash
systemctl --user restart snowgrid-display
```

To check which monitor it will use without starting feh:
`DISPLAY=:0 .venv/bin/python -m snowgrid.display --dry-run`

### Replacing another app on that monitor

Two apps on one monitor will cover each other, so turn the old one off. For
example, for `LIDAR_UIBK` (started from the desktop autostart):

```bash
rm ~/.config/autostart/lidar-uibk.desktop   # don't start it at login any more
pkill -f lidar_uibk.py                      # stop the running one
systemctl --user restart snowgrid-display
```

Other apps work the same way: look in `~/.config/autostart/` for `.desktop`
files, or check `systemctl --user list-units --type=service` for ones set up by
`setup_pi.sh` (`systemctl --user disable --now <name>`).

---

## Configuration

Everything is in `config.toml`:

| Section | Keys |
|---|---|
| `[paths]` | `output_dir`, `cache_dir`, `natural_earth_dir` (relative to the config file), `keep_days` |
| `[schedule]` | `interval_hours`: timer interval (re-run `install.sh` after changing) |
| `[api]` | `base_url`, `parameter`, `timeout_s`, `retries`, `backoff_s`, `max_backoff_s` |
| `[image]` | `width`, `height` (default 1920×1080), `dpi`, colours (`background`, `foreground`, `land`, `border`, `state_border`, `water`) |
| `[depth]` | `levels` and one colour per level in `colors` (the last colour is the 200+ class), `no_snow_threshold_cm` |
| `[change]` | `limit_cm` (±30), `cmap` (`berlin_r`, which needs matplotlib ≥ 3.10), `fallback_cmap` |
| `[display]` | `enabled`, `reload_s`, `slideshow_delay_s`, `screen` (0 = leftmost monitor) |
| `[[cities]]` | `name`, `lon`, `lat`, optional `align = "right"` to put the label left of the dot |

Requests retry on timeouts, connection errors, HTTP 429 and 5xx, with
exponential backoff: `backoff_s × 2ⁿ`, capped at `max_backoff_s`. For 429 the
server's `Retry-After` / `ratelimit-reset` is honoured. Other 4xx errors fail
at once.

---

## Troubleshooting

**`journalctl` shows `run failed: … giving up after 6 attempts`**
The API or the network was unreachable. The old images stay on screen and the
next timer run tries again. Test the API with:
`curl -s https://dataset.api.hub.geosphere.at/v1/grid/historical/snowgrid_cl-v2-1d-1km/metadata | head`

**`… is outside the available range …`**
`--date` is later than the metadata `end_time` (the model runs a few days
behind) or earlier than 1961-01-02.

**Images don't change for days**
This is normal when GeoSphere hasn't published a new day yet: the log says
`images for … are up to date`. Compare with the metadata `end_time`.

**`another snowgrid run holds …/.lock; skipping this run`**
A manual run and a timer run overlapped. The second one exits harmlessly.

**Black screen / no slideshow**
`systemctl --user status snowgrid-display`. Check that the desktop
auto-logs in on X11 (see above), that `ls /tmp/.X11-unix/X0` exists, and that
`output/snow_depth.png` exists. Start the display by hand to see errors:
`DISPLAY=:0 feh --fullscreen output/snow_depth.png`.

**`config.toml is invalid` / exit status 2**
The message names the section and key. Fix it and run `--once` again.

**Natural Earth download failed during install**
Network problem. Re-run `./install.sh`. Once downloaded, plotting never needs
the network again.

**cartopy fails to install with pip**
You are probably not on a 64-bit OS (`uname -m` should print `aarch64`). On
other architectures `install.sh` uses apt's `python3-cartopy` automatically.
Delete `.venv` and run `./install.sh` again.

**Change the image size**
Set `[image] width/height` (e.g. 1280×720 or portrait 1080×1920), then run
`.venv/bin/python -m snowgrid.main --once --force`.
