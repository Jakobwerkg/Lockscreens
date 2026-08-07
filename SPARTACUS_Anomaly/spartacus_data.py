"""
Data layer for SPARTACUS v3 (Austria, 1 km, daily) from the GeoSphere data hub.

https://data.hub.geosphere.at/dataset/spartacus-v3-1d-1km

Provides
  latest_available_date()          – last day the archive currently offers
  fetch_window(end_date, n_days)   – observed daily grids for the last n days
  climatology(dates)               – 1991–2020 mean grid for each calendar day
  build_report(...)                – observed 7-day mean, climate mean, anomaly

Grids are numpy arrays of shape (329, 584) = (south→north, west→east);
cells outside Austria are NaN.  Everything is cached under ./cache/.
"""

import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import requests
from netCDF4 import Dataset, num2date

# ── API ──────────────────────────────────────────────────────────────────────
API_BASE  = "https://dataset.api.hub.geosphere.at/v1/grid/historical/spartacus-v3-1d-1km"
META_URL  = API_BASE + "/metadata"
BBOX      = "46.16,9.39,49.18,17.39"        # whole Austrian domain
PARAMS    = ("RR", "SA", "TM24", "TN", "TX")

CLIM_FIRST_YEAR, CLIM_LAST_YEAR = 1991, 2020
WINDOW_DAYS = 7

# API allows 5 requests/s and 240/h – stay well clear of both.
REQUEST_PAUSE = 0.8
MAX_RETRIES   = 4

CACHE_DIR = Path(__file__).parent / "cache"
CLIM_DIR  = CACHE_DIR / "clim"
DL_DIR    = CACHE_DIR / "download"

# Human-readable metadata for every parameter we use.
PARAM_INFO = {
    "RR":   dict(label="Precipitation",     unit="mm/day", long="daily precipitation sum"),
    "SA":   dict(label="Sunshine",          unit="h/day",  long="daily sunshine duration"),
    "TM24": dict(label="Mean temperature",  unit="°C",     long="daily mean of air temperature"),
    "TN":   dict(label="Minimum temp.",     unit="°C",     long="daily minimum of air temperature"),
    "TX":   dict(label="Maximum temp.",     unit="°C",     long="daily maximum of air temperature"),
}


def _log(msg):
    print(f"[SPARTACUS] {msg}", flush=True)


# ── raw API access ───────────────────────────────────────────────────────────
def latest_available_date():
    """Last day currently served by the archive (falls back to 'yesterday')."""
    try:
        meta = requests.get(META_URL, timeout=30).json()
        return datetime.fromisoformat(meta["end_time"]).date()
    except Exception as exc:
        _log(f"metadata unavailable ({exc}) – assuming yesterday")
        return date.today() - timedelta(days=1)


def _download(start: date, end: date, dest: Path) -> Path:
    """Fetch one NetCDF covering [start, end] for all parameters."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    query = [("parameters", p) for p in PARAMS] + [
        ("start", f"{start:%Y-%m-%d}T00:00"),
        ("end",   f"{end:%Y-%m-%d}T00:00"),
        ("bbox", BBOX),
        ("output_format", "netcdf"),
    ]

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with requests.get(API_BASE, params=query, timeout=180, stream=True) as r:
                if r.status_code == 429:                      # rate limited
                    wait = int(r.headers.get("Retry-After", 5 * attempt))
                    _log(f"rate limited – waiting {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
            tmp.replace(dest)
            time.sleep(REQUEST_PAUSE)
            return dest
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            if attempt == MAX_RETRIES:
                raise
            _log(f"download {start}…{end} failed ({exc}) – retry {attempt}/{MAX_RETRIES}")
            time.sleep(3 * attempt)

    raise RuntimeError("unreachable")


def _read(path: Path):
    """→ (list[date], {param: (n, 329, 584) float32}, coords)

    `coords` carries the 2-D lat/lon plus the 1-D EPSG:3416 axes: `easting`
    runs along the last dimension, `northing` along the second-to-last.
    """
    with Dataset(path) as nc:
        tvar  = nc.variables["time"]
        times = num2date(tvar[:], tvar.units, only_use_cftime_datetimes=False)
        dates = [datetime(t.year, t.month, t.day).date() for t in np.atleast_1d(times)]

        fields = {}
        for p in PARAMS:
            arr = np.ma.filled(nc.variables[p][:].astype("float32"), np.nan)
            fields[p] = np.atleast_3d(arr).reshape(len(dates), *arr.shape[-2:])

        coords = dict(
            lat=np.ma.filled(nc.variables["lat"][:].astype("float32"), np.nan),
            lon=np.ma.filled(nc.variables["lon"][:].astype("float32"), np.nan),
            easting=np.asarray(nc.variables["x"][:], dtype="float64"),
            northing=np.asarray(nc.variables["y"][:], dtype="float64"),
        )

    # Sunshine duration comes in seconds – hours read much better on a display.
    fields["SA"] = fields["SA"] / 3600.0
    return dates, fields, coords


# ── observed window ──────────────────────────────────────────────────────────
def fetch_window(end_date: date, n_days: int = WINDOW_DAYS):
    """Observed daily grids for the n_days ending on (and including) end_date."""
    start = end_date - timedelta(days=n_days - 1)
    path  = DL_DIR / f"obs_{start:%Y%m%d}_{end_date:%Y%m%d}.nc"
    _log(f"observations {start} … {end_date}")
    _download(start, end_date, path)
    dates, fields, coords = _read(path)

    # Drop trailing days that are still empty (the archive publishes with a lag).
    while dates and np.isnan(fields["TX"][-1]).mean() > 0.95:
        _log(f"{dates[-1]} not populated yet – dropping")
        dates = dates[:-1]
        fields = {p: v[:-1] for p, v in fields.items()}

    if not dates:
        raise RuntimeError("no populated days in the requested window")
    return dates, fields, coords


# ── 1991–2020 climatology ────────────────────────────────────────────────────
def _clim_path(month: int, day: int) -> Path:
    return CLIM_DIR / f"clim_{month:02d}-{day:02d}.npz"


def _build_clim_for(days_needed, ref_year: int):
    """Download 1991–2020 and store a mean grid for each (month, day) needed.

    `days_needed` holds the actual dates of the current window; `ref_year` is
    the year of its last day, so a window spanning New Year keeps its offsets.
    """
    keys  = [(d.month, d.day) for d in days_needed]
    shape = None
    total = {k: None for k in keys}
    count = {k: None for k in keys}

    for year in range(CLIM_FIRST_YEAR, CLIM_LAST_YEAR + 1):
        shift = year - ref_year
        mapped = []
        for d in days_needed:
            try:
                mapped.append(d.replace(year=d.year + shift))
            except ValueError:                      # 29 Feb in a non-leap year
                mapped.append(d.replace(year=d.year + shift, day=28))

        start, end = min(mapped), max(mapped)
        path = DL_DIR / f"clim_{start:%Y%m%d}_{end:%Y%m%d}.nc"
        _log(f"climatology {year} ({start} … {end})")
        _download(start, end, path)
        dates, fields, _ = _read(path)

        for i, d in enumerate(dates):
            key = (d.month, d.day)
            if key not in total:
                continue                            # e.g. 29 Feb padding
            for p in PARAMS:
                grid = fields[p][i]
                if shape is None:
                    shape = grid.shape
                if total[key] is None:
                    total[key] = {q: np.zeros(shape, "float32") for q in PARAMS}
                    count[key] = {q: np.zeros(shape, "int16")   for q in PARAMS}
                valid = np.isfinite(grid)
                total[key][p][valid] += grid[valid]
                count[key][p][valid] += 1

        path.unlink(missing_ok=True)                # raw file no longer needed

    CLIM_DIR.mkdir(parents=True, exist_ok=True)
    for key in keys:
        if total[key] is None:
            continue
        means = {}
        for p in PARAMS:
            n = count[key][p]
            with np.errstate(invalid="ignore", divide="ignore"):
                m = np.where(n > 0, total[key][p] / np.maximum(n, 1), np.nan)
            means[p] = m.astype("float32")
        np.savez_compressed(_clim_path(*key), n_years=count[key]["TX"].max(), **means)
        _log(f"climatology cached for {key[0]:02d}-{key[1]:02d}")


def climatology(days):
    """1991–2020 daily mean grid for every date in `days` → {param: (n, H, W)}."""
    missing = [d for d in days if not _clim_path(d.month, d.day).exists()]
    if missing:
        _log(f"building climatology for {len(missing)} new calendar day(s) "
             f"– {CLIM_FIRST_YEAR}–{CLIM_LAST_YEAR}, this takes a few minutes")
        _build_clim_for(missing, ref_year=days[-1].year)

    stacks = {p: [] for p in PARAMS}
    n_years = 0
    for d in days:
        path = _clim_path(d.month, d.day)
        if not path.exists() and (d.month, d.day) == (2, 29):
            path = _clim_path(2, 28)                # leap day → use 28 Feb
        with np.load(path) as z:
            n_years = max(n_years, int(z["n_years"]))
            for p in PARAMS:
                stacks[p].append(z[p])
    return {p: np.stack(v) for p, v in stacks.items()}, n_years


def prune_climatology_cache(today: date, keep_days: int = 45):
    """Drop cached calendar days far from today so the SD card stays small."""
    if not CLIM_DIR.exists():
        return
    for path in CLIM_DIR.glob("clim_??-??.npz"):
        try:
            month, day = (int(x) for x in path.stem.split("_")[1].split("-"))
            doy   = date(2020, month, day).timetuple().tm_yday
            today_doy = today.replace(year=2020).timetuple().tm_yday
            dist = abs(doy - today_doy)
            if min(dist, 366 - dist) > keep_days:
                path.unlink()
        except Exception:
            continue


# ── window mean + anomaly ────────────────────────────────────────────────────
def build_report(end_date: date = None, n_days: int = WINDOW_DAYS):
    """Everything the plot needs, in one dict."""
    end_date = end_date or latest_available_date()
    dates, obs, coords = fetch_window(end_date, n_days)
    clim, n_years = climatology(dates)

    result = {}
    for p in PARAMS:
        with np.errstate(invalid="ignore"):
            obs_mean  = np.nanmean(obs[p],  axis=0)
            clim_mean = np.nanmean(clim[p], axis=0)
            diff      = obs_mean - clim_mean
            if p == "RR":
                # Precipitation reads far better as a percentage departure:
                # +/- x % of what normally falls on these calendar days.
                anomaly = np.where(clim_mean > 0.05,
                                   100.0 * (obs_mean / clim_mean - 1.0), np.nan)
            else:
                anomaly = diff
        result[p] = dict(observed=obs_mean, climate=clim_mean,
                         anomaly=anomaly, difference=diff)

    prune_climatology_cache(dates[-1])
    for stale in DL_DIR.glob("obs_*.nc"):
        if stale.stem != f"obs_{dates[0]:%Y%m%d}_{end_date:%Y%m%d}":
            stale.unlink(missing_ok=True)

    return dict(fields=result, dates=dates, coords=coords,
                n_years=n_years, generated=datetime.now())


if __name__ == "__main__":
    rep = build_report()
    print(f"{rep['dates'][0]} … {rep['dates'][-1]}  ({rep['n_years']} climate years)")
    print(f"{'':5s} {'observed':>10s} {'normal':>10s} {'mean anomaly':>14s}")
    for p in PARAMS:
        f = rep["fields"][p]
        # RR: the national figure is the ratio of the two area means, not the
        # area mean of the per-cell ratios (those are not the same number).
        if p == "RR":
            obs, clim = np.nanmean(f["observed"]), np.nanmean(f["climate"])
            anom = f"{100 * (obs / clim - 1):+.1f} %"
        else:
            obs, clim = np.nanmean(f["observed"]), np.nanmean(f["climate"])
            anom = f"{np.nanmean(f['difference']):+.2f}"
        print(f"  {p:5s} {obs:10.2f} {clim:10.2f} {anom:>14s}")
