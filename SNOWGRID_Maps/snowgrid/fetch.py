"""Metadata, download and cache for GeoSphere SNOWGRID-CL v2.1 (daily, 1 km).

API: https://dataset.api.hub.geosphere.at/v1/docs/

* ``GET <base>/metadata`` gives ``end_time`` (the latest day available), the
  lat/lon ``bbox`` of the domain and the CRS (EPSG:3416).
* ``GET <base>?parameters=snow_depth&start=…&end=…&bbox=S,W,N,E&output_format=netcdf``
  returns one NetCDF holding every day in ``[start, end]`` (both inclusive).

Request limits (docs, "Request Limit"): 5 requests/s, 240 requests/h, and at most
10 000 000 values per NetCDF request. One run makes one metadata request plus at
most one data request of 1 parameter x 2 days x 329 x 584 cells = 384 272 values.

Each cached file ``snowgrid_<YYYY-MM-DD>.nc`` holds that day and the day before,
which is everything needed for both maps.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import requests
import xarray as xr

from snowgrid import __version__
from snowgrid.config import ApiConfig

log = logging.getLogger(__name__)

CACHE_PATTERN = re.compile(r"^snowgrid_(\d{4}-\d{2}-\d{2})\.nc$")
UNIT_TO_CM = {"m": 100.0, "cm": 1.0, "mm": 0.1}
USER_AGENT = f"snowgrid-display/{__version__} (+https://dataset.api.hub.geosphere.at)"


class FetchError(RuntimeError):
    """Raised when metadata or data cannot be obtained or is invalid."""


@dataclass(frozen=True)
class Metadata:
    """The parts of the dataset metadata this app uses."""

    start: date
    end: date
    bbox: tuple[float, float, float, float]  # south, west, north, east
    crs: str
    unit: str


@dataclass
class SnowPair:
    """Snow depth for one day and the day before, in cm, on the native grid.

    Arrays have shape ``(ny, nx)`` with ``y`` increasing northwards (row 0 is
    the southernmost row). Cells outside the model domain are NaN.
    """

    day: date
    latest_cm: np.ndarray
    previous_cm: np.ndarray
    x: np.ndarray
    y: np.ndarray

    @property
    def change_cm(self) -> np.ndarray:
        """24 h change: latest minus previous day."""
        return self.latest_cm - self.previous_cm

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """Grid extent as cell *edges* ``(x0, x1, y0, y1)`` in EPSG:3416 metres."""
        dx = float(self.x[1] - self.x[0])
        dy = float(self.y[1] - self.y[0])
        return (
            float(self.x[0]) - dx / 2,
            float(self.x[-1]) + dx / 2,
            float(self.y[0]) - dy / 2,
            float(self.y[-1]) + dy / 2,
        )


# ── HTTP ─────────────────────────────────────────────────────────────────────
def make_session() -> requests.Session:
    """Return a ``requests`` session with a descriptive User-Agent."""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _retry_wait(api: ApiConfig, attempt: int, resp: requests.Response | None) -> float:
    """Seconds to wait before retry number ``attempt`` (0-based).

    Exponential backoff ``backoff_s * 2**attempt``, capped at ``max_backoff_s``.
    For HTTP 429 the server's ``Retry-After`` / ``ratelimit-reset`` header wins
    if it asks for a longer wait.
    """
    wait = min(api.backoff_s * (2**attempt), api.max_backoff_s)
    if resp is not None and resp.status_code == 429:
        for header in ("Retry-After", "ratelimit-reset"):
            value = resp.headers.get(header)
            if value and value.strip().isdigit():
                wait = max(wait, min(float(value), 3600.0))
                break
    return wait


def http_get(
    session: requests.Session,
    url: str,
    api: ApiConfig,
    params: list[tuple[str, str]] | None = None,
    stream: bool = False,
) -> requests.Response:
    """GET ``url`` with timeouts and retries with exponential backoff.

    Retries on connection errors, timeouts, HTTP 429 and HTTP 5xx. Any other
    HTTP error (e.g. 400 for a bad query or 422 for a date out of range) is
    raised at once because retrying cannot fix it.

    Raises:
        FetchError: when all attempts fail or the server rejects the request.
    """
    last_error = "no attempt made"
    for attempt in range(api.retries + 1):
        resp: requests.Response | None = None
        try:
            resp = session.get(url, params=params, timeout=api.timeout_s, stream=stream)
            if resp.status_code == 200:
                return resp
            body = " ".join(resp.text[:300].split()) if not stream else ""
            last_error = f"HTTP {resp.status_code} {resp.reason} {body}".strip()
            if resp.status_code != 429 and resp.status_code < 500:
                resp.close()
                raise FetchError(f"{url}: {last_error}")
            resp.close()
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < api.retries:
            wait = _retry_wait(api, attempt, resp)
            log.warning(
                "request failed (%s), retry %d/%d in %.0f s",
                last_error, attempt + 1, api.retries, wait,
            )
            time.sleep(wait)
    raise FetchError(f"{url}: giving up after {api.retries + 1} attempts: {last_error}")


# ── metadata ─────────────────────────────────────────────────────────────────
def _parse_day(value: str) -> date:
    """Parse an API timestamp such as ``2026-11-21T00:00+00:00`` to a UTC date."""
    return datetime.fromisoformat(value).date()


def get_metadata(session: requests.Session, api: ApiConfig) -> Metadata:
    """Fetch and parse the dataset metadata.

    Raises:
        FetchError: if the request fails or the response lacks required fields.
    """
    resp = http_get(session, api.metadata_url, api)
    try:
        meta = resp.json()
        bbox = tuple(float(v) for v in meta["bbox"])
        if len(bbox) != 4:
            raise ValueError(f"bbox has {len(bbox)} values")
        units = {p["name"]: p.get("unit", "") for p in meta.get("parameters", [])}
        if api.parameter not in units:
            raise ValueError(f"parameter '{api.parameter}' not offered by the dataset")
        return Metadata(
            start=_parse_day(meta["start_time"]),
            end=_parse_day(meta["end_time"]),
            bbox=bbox,  # type: ignore[arg-type]
            crs=str(meta.get("crs", "")),
            unit=units[api.parameter],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise FetchError(f"unexpected metadata from {api.metadata_url}: {exc}") from exc


# ── cache ────────────────────────────────────────────────────────────────────
def cache_file(cache_dir: Path, day: date) -> Path:
    """Path of the cached NetCDF holding ``day`` and ``day - 1``."""
    return cache_dir / f"snowgrid_{day.isoformat()}.nc"


def cached_days(cache_dir: Path) -> list[date]:
    """All days with a cache file, oldest first."""
    days: list[date] = []
    if cache_dir.is_dir():
        for p in cache_dir.iterdir():
            m = CACHE_PATTERN.match(p.name)
            if m:
                days.append(date.fromisoformat(m.group(1)))
    return sorted(days)


def _validate_file(path: Path, parameter: str, day: date) -> None:
    """Check that ``path`` is a readable NetCDF with ``parameter`` for day-1 and day.

    Raises:
        FetchError: if the file is unreadable or incomplete.
    """
    wanted = [np.datetime64(day - timedelta(days=1)), np.datetime64(day)]
    try:
        with xr.open_dataset(path, drop_variables=["lat", "lon"]) as ds:
            if parameter not in ds:
                raise FetchError(f"{path.name}: variable '{parameter}' missing")
            times = ds["time"].values.astype("datetime64[D]")
            missing = [str(t) for t in wanted if t not in times]
            if missing:
                raise FetchError(f"{path.name}: time steps missing: {', '.join(missing)}")
    except FetchError:
        raise
    except Exception as exc:  # netCDF4/HDF5 raise a wide variety of errors
        raise FetchError(f"{path.name}: unreadable NetCDF ({exc})") from exc


def download_pair(
    session: requests.Session,
    api: ApiConfig,
    meta: Metadata,
    day: date,
    dest: Path,
) -> Path:
    """Download ``day - 1`` and ``day`` in a single NetCDF request to ``dest``.

    The file is written to ``dest.part`` first, validated, and only then
    renamed, so ``dest`` is either complete or absent.
    """
    prev = day - timedelta(days=1)
    s, w, n, e = meta.bbox
    params = [
        ("parameters", api.parameter),
        ("start", f"{prev.isoformat()}T00:00"),
        ("end", f"{day.isoformat()}T00:00"),
        ("bbox", f"{s!r},{w!r},{n!r},{e!r}"),
        ("output_format", "netcdf"),
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log.info("downloading %s for %s and %s", api.parameter, prev, day)
    t0 = time.monotonic()
    resp = http_get(session, api.base_url, api, params=params, stream=True)
    size = 0
    try:
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                fh.write(chunk)
                size += len(chunk)
            fh.flush()
            os.fsync(fh.fileno())
    except (OSError, requests.RequestException) as exc:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"download interrupted: {exc}") from exc
    finally:
        resp.close()

    try:
        _validate_file(tmp, api.parameter, day)
    except FetchError:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, dest)
    log.info(
        "saved %s (%.1f kB, %s values, %.1f s)",
        dest.name, size / 1024, resp.headers.get("datapoint-count", "?"), time.monotonic() - t0,
    )
    return dest


def ensure_cached(
    session: requests.Session,
    api: ApiConfig,
    meta: Metadata | None,
    cache_dir: Path,
    day: date,
    force: bool = False,
) -> Path:
    """Return the cache file for ``day``, downloading it if needed.

    If a valid file already exists and ``force`` is false, no request is made.
    ``meta`` may be ``None`` only if the file is already cached.

    Raises:
        FetchError: if the data cannot be downloaded or ``day`` is out of range.
    """
    dest = cache_file(cache_dir, day)
    if dest.exists() and not force:
        try:
            _validate_file(dest, api.parameter, day)
            log.info("%s already cached, skipping download", day)
            return dest
        except FetchError as exc:
            log.warning("discarding bad cache file: %s", exc)
            dest.unlink(missing_ok=True)

    if meta is None:
        raise FetchError(f"{day} is not cached and the metadata is unavailable")
    if not (meta.start + timedelta(days=1) <= day <= meta.end):
        raise FetchError(
            f"{day} is outside the available range "
            f"{meta.start + timedelta(days=1)} … {meta.end}"
        )
    return download_pair(session, api, meta, day, dest)


def prune_cache(cache_dir: Path, newest: date, keep_days: int, protect: Path | None = None) -> None:
    """Delete cache files older than ``keep_days`` days before ``newest``.

    Leftover ``.part`` files from interrupted downloads are removed too.
    ``protect`` (the file in use) is never deleted.
    """
    if not cache_dir.is_dir():
        return
    cutoff = newest - timedelta(days=keep_days - 1)
    for p in cache_dir.iterdir():
        if p == protect:
            continue
        m = CACHE_PATTERN.match(p.name)
        if (m and date.fromisoformat(m.group(1)) < cutoff) or p.name.endswith(".nc.part"):
            try:
                p.unlink()
                log.info("pruned %s", p.name)
            except OSError as exc:
                log.warning("could not delete %s: %s", p, exc)


# ── reading ──────────────────────────────────────────────────────────────────
def load_pair(path: Path, parameter: str, day: date, source_unit: str = "m") -> SnowPair:
    """Read ``day - 1`` and ``day`` from ``path`` and convert to centimetres.

    The unit comes from the variable's ``units`` attribute, falling back to
    ``source_unit`` (from the metadata) if the file has none. Only the one parameter and the two time steps are loaded, as float32, and
    the file is closed before returning.

    Raises:
        FetchError: if the unit is unknown or the data is entirely missing.
    """
    prev = day - timedelta(days=1)
    with xr.open_dataset(path, drop_variables=["lat", "lon"]) as ds:
        da = ds[parameter]
        unit = str(da.attrs.get("units") or source_unit).strip().lower()
        factor = UNIT_TO_CM.get(unit)
        if factor is None:
            raise FetchError(f"unknown unit '{unit}' for {parameter}")
        da = da.sortby("y")  # row 0 = south, so origin='lower' puts north on top
        times = da["time"].values.astype("datetime64[D]")
        i_prev = int(np.nonzero(times == np.datetime64(prev))[0][0])
        i_day = int(np.nonzero(times == np.datetime64(day))[0][0])
        latest = (da.isel(time=i_day).values * factor).astype(np.float32)
        previous = (da.isel(time=i_prev).values * factor).astype(np.float32)
        x = da["x"].values.astype(np.float64)
        y = da["y"].values.astype(np.float64)

    if x.size < 2 or y.size < 2:
        raise FetchError(f"{path.name}: grid too small ({y.size} x {x.size})")
    if not np.isfinite(latest).any():
        raise FetchError(f"{path.name}: {day} contains no valid values")
    if not np.isfinite(previous).any():
        raise FetchError(f"{path.name}: {prev} contains no valid values")
    # Physically snow depth is >= 0; clip tiny negative numerical noise.
    np.maximum(latest, 0, out=latest, where=np.isfinite(latest))
    np.maximum(previous, 0, out=previous, where=np.isfinite(previous))
    return SnowPair(day=day, latest_cm=latest, previous_cm=previous, x=x, y=y)
