# SPARTACUS 7-day climate anomaly

Fullscreen dashboard showing how the **last 7 days in Austria** compare to the
**1991–2020 normal**, on the full 1 km SPARTACUS v3 grid.

Data: [GeoSphere Austria – SPARTACUS v3, daily, 1 km](https://data.hub.geosphere.at/dataset/spartacus-v3-1d-1km) (CC BY 4.0)

---

## What it shows

Six cards on one screen — five maps plus a summary:

| Card | Parameter | Anomaly shown as |
|---|---|---|
| Mean temperature | `TM24` – daily mean of air temperature | K difference |
| Minimum temp. | `TN` – daily minimum | K difference |
| Maximum temp. | `TX` – daily maximum | K difference |
| Precipitation | `RR` – daily precipitation sum | ± % of normal |
| Sunshine | `SA` – daily sunshine duration | hours/day difference |
| Summary | all five | Austria-wide averages |

Precipitation is a signed percentage departure — `-29 %` means 29 % less rain
than normally falls on those calendar days — because a millimetre difference
means something very different in the Alps than in the Pannonian east. Every
other field is an absolute difference.

Each map has its own discrete colour bar, and each card carries the
Austria-wide mean anomaly as a badge.

### Borders

The Austrian national border is drawn in white and the surrounding national
borders in grey, from the vendored `borders.npz` (Natural Earth 1:10 m, public
domain). Longitude/latitude are converted to the grid with an inline
EPSG:3416 (Austria Lambert) projection, so no `cartopy`/`pyproj` is needed.

The border matters here: SPARTACUS is interpolated onto a domain somewhat
larger than Austria, so the coloured area extends past the frontier into
Bavaria, Bohemia and Slovakia. The white line is where Austria actually ends.

---

## How it works

**On every startup**, and every 6 hours after that for as long as it keeps
running:

1. Ask the archive for the latest available day (it publishes with a lag of
   1–2 days, and the last 7 days are still being quality-corrected).
2. Download the **7 most recent days** for the whole Austrian domain, all five
   parameters, as one NetCDF (~3.4 MB).
3. Average each parameter over those 7 days.
4. Compare against the **1991–2020 mean for the same calendar days** — i.e. the
   normal for "31 Jul – 6 Aug", not a monthly or annual mean.
5. Render the dashboard to a PNG sized to the screen and display it.

### Climatology cache

The 30-year normal is not offered by the API for `RR`, `SA`, `TN` and `TX`, so
it is computed once per calendar day and cached in `cache/clim/clim_MM-DD.npz`:

* **first run** – 30 requests (one per year, each covering the 7-day window),
  roughly 100 MB and a few minutes;
* **every day after** – only the one new calendar day is missing, so 30 small
  requests, about 15 MB.

Each cached calendar day is about 1.4 MB. Days more than 45 days from today are
deleted automatically, so the cache settles at roughly 130 MB instead of growing
all year.

The API allows 5 requests/second and 240/hour; the client paces itself well
inside both and backs off on HTTP 429.

---

## How long a start takes

Response time per API call is roughly 2.5–5 s and is dominated by server
latency, not by how much data is asked for — so the cost of an update is
mostly *how many requests* it needs, not how many megabytes.

| Phase | Mac (measured) | Pi 4 (estimate) |
|---|---|---|
| Boot to desktop autologin | — | 30–45 s |
| Python imports + window up | 0.5 s | 8–15 s |
| **→ last render visible** | — | **≈ 1 min after power-on** |
| Metadata + 7-day download | 5 s | 5–10 s |
| Climatology (already cached) | 0.1 s | 1–2 s |
| Render the PNG | 0.4 s | 3–5 s |
| **→ fresh dashboard, same day** | ≈ 6 s | **≈ 15–20 s** |
| 30 requests for one new calendar day | 1.5–2 min | 2–3 min |
| **→ fresh dashboard, new day** | ≈ 2 min | **≈ 3 min** |
| **→ first run ever, empty cache** | ≈ 3 min | **≈ 4–5 min** |

The screen is never blank while any of this happens: the previous render is
shown immediately and the fetch runs on a background thread behind it. Only
the very first run — with no cached PNG — shows a progress message instead.

Note that a new calendar day always costs 30 requests, one per climatology
year, no matter that it is a single day's worth of data. That is why the
daily update takes minutes rather than seconds even though it only moves
about 15 MB.

---

## Running it

```bash
python3 spartacus_anomaly.py --screen 0
```

Keys: `Q` / `Esc` quit, `R` refresh now.

There is no fixed update time — a restart is always a refresh. If a rendered
PNG is already on disk it appears immediately so the screen is never blank,
while the current data is fetched behind it.

Repeated restarts on the same day are cheap: the 7-day window is cached under
its own date range, so the NetCDF is only re-downloaded once the archive
publishes a new day.

Render a PNG without the GUI (useful for testing):

```bash
python3 spartacus_plot.py
```

Print the Austria-wide numbers only:

```bash
python3 spartacus_data.py
```

---

## Setup on the Pi

```bash
bash install_pi.sh
bash setup_autostart.sh 0      # argument = monitor index
```

Dependencies: `python3-tk python3-pil python3-pil.imagetk python3-numpy
python3-matplotlib python3-netcdf4 python3-requests`.

---

## Files

| File | Purpose |
|---|---|
| `spartacus_data.py` | API access, download cache, 1991–2020 climatology, anomalies |
| `spartacus_plot.py` | Renders the dashboard PNG |
| `borders.npz` | National borders, lon/lat (Natural Earth 1:10 m, public domain) |
| `spartacus_anomaly.py` | Fullscreen Tk app, refreshes on startup and every 6 h |
| `cache/` | NetCDF downloads, climatology `.npz`, rendered PNG (git-ignored) |
