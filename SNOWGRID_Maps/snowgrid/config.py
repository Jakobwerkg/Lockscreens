"""Load and validate ``config.toml``.

All relative paths in the config file are resolved against the directory
that contains the config file, so the app works no matter what the current
working directory is (systemd, cron, manual runs).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when ``config.toml`` is missing a value or has an invalid one."""


@dataclass(frozen=True)
class ApiConfig:
    """GeoSphere dataset API settings."""

    base_url: str
    parameter: str
    timeout_s: float
    retries: int
    backoff_s: float
    max_backoff_s: float

    @property
    def metadata_url(self) -> str:
        """URL of the dataset's metadata endpoint."""
        return f"{self.base_url}/metadata"


@dataclass(frozen=True)
class ImageConfig:
    """Output image size and colours."""

    width: int
    height: int
    dpi: int
    background: str
    foreground: str
    land: str
    border: str
    state_border: str
    water: str


@dataclass(frozen=True)
class DepthStyle:
    """Colour classes for the snow depth map."""

    levels: list[float]
    colors: list[str]
    no_snow_threshold_cm: float


@dataclass(frozen=True)
class ChangeStyle:
    """Colour scale for the 24 h change map."""

    limit_cm: float
    cmap: str
    fallback_cmap: str


@dataclass(frozen=True)
class City:
    """A labelled city on the map."""

    name: str
    lon: float
    lat: float
    align: str = "left"


@dataclass(frozen=True)
class DisplayConfig:
    """Settings for the optional feh slideshow."""

    enabled: bool
    reload_s: int
    slideshow_delay_s: int


@dataclass(frozen=True)
class Config:
    """Complete, validated application configuration."""

    path: Path
    output_dir: Path
    cache_dir: Path
    natural_earth_dir: Path
    keep_days: int
    interval_hours: int
    api: ApiConfig
    image: ImageConfig
    depth: DepthStyle
    change: ChangeStyle
    cities: list[City] = field(default_factory=list)
    display: DisplayConfig = field(default_factory=lambda: DisplayConfig(True, 60, 30))
    fingerprint: str = ""

    @property
    def archive_dir(self) -> Path:
        """Directory holding the dated PNG copies."""
        return self.output_dir / "archive"


def _get(table: dict[str, Any], key: str, kind: type | tuple[type, ...], section: str) -> Any:
    """Return ``table[key]`` after checking that it exists and has the right type."""
    if key not in table:
        raise ConfigError(f"[{section}] is missing '{key}'")
    value = table[key]
    # bool is a subclass of int, so reject it explicitly for numeric fields.
    if isinstance(value, bool) and bool not in (kind if isinstance(kind, tuple) else (kind,)):
        raise ConfigError(f"[{section}] '{key}' must not be a boolean")
    if not isinstance(value, kind):
        raise ConfigError(f"[{section}] '{key}' has the wrong type ({type(value).__name__})")
    return value


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the TOML table ``name`` or raise a helpful error."""
    table = raw.get(name)
    if not isinstance(table, dict):
        raise ConfigError(f"missing section [{name}]")
    return table


def _resolve(base: Path, value: str) -> Path:
    """Resolve ``value`` relative to ``base`` unless it is absolute; expand ``~``."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load_config(path: str | Path) -> Config:
    """Read ``config.toml`` from ``path`` and return a validated :class:`Config`.

    Raises:
        ConfigError: if the file is missing or any value is invalid.
    """
    cfg_path = Path(path).expanduser().resolve()
    try:
        data = cfg_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read config file {cfg_path}: {exc}") from exc
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"invalid TOML in {cfg_path}: {exc}") from exc

    base = cfg_path.parent
    num = (int, float)

    paths = _section(raw, "paths")
    sched = _section(raw, "schedule")
    api_t = _section(raw, "api")
    img_t = _section(raw, "image")
    dep_t = _section(raw, "depth")
    chg_t = _section(raw, "change")
    disp_t = _section(raw, "display")

    api = ApiConfig(
        base_url=str(_get(api_t, "base_url", str, "api")).rstrip("/"),
        parameter=_get(api_t, "parameter", str, "api"),
        timeout_s=float(_get(api_t, "timeout_s", num, "api")),
        retries=int(_get(api_t, "retries", int, "api")),
        backoff_s=float(_get(api_t, "backoff_s", num, "api")),
        max_backoff_s=float(_get(api_t, "max_backoff_s", num, "api")),
    )
    if api.retries < 0 or api.timeout_s <= 0 or api.backoff_s < 0:
        raise ConfigError("[api] retries must be >= 0, timeout_s > 0, backoff_s >= 0")

    image = ImageConfig(
        width=_get(img_t, "width", int, "image"),
        height=_get(img_t, "height", int, "image"),
        dpi=_get(img_t, "dpi", int, "image"),
        background=_get(img_t, "background", str, "image"),
        foreground=_get(img_t, "foreground", str, "image"),
        land=_get(img_t, "land", str, "image"),
        border=_get(img_t, "border", str, "image"),
        state_border=_get(img_t, "state_border", str, "image"),
        water=_get(img_t, "water", str, "image"),
    )
    if not (320 <= image.width <= 8000 and 240 <= image.height <= 8000):
        raise ConfigError("[image] width/height must be between 320x240 and 8000x8000")
    if not 30 <= image.dpi <= 600:
        raise ConfigError("[image] dpi must be between 30 and 600")

    levels = [float(v) for v in _get(dep_t, "levels", list, "depth")]
    colors = [str(c) for c in _get(dep_t, "colors", list, "depth")]
    if len(levels) < 2 or any(b <= a for a, b in zip(levels, levels[1:])):
        raise ConfigError("[depth] levels must be at least two strictly increasing numbers")
    if len(colors) != len(levels):
        raise ConfigError(
            f"[depth] needs one colour per level ({len(levels)}): one per class "
            f"between levels plus one for values above the last level"
        )
    depth = DepthStyle(
        levels=levels,
        colors=colors,
        no_snow_threshold_cm=float(_get(dep_t, "no_snow_threshold_cm", num, "depth")),
    )

    change = ChangeStyle(
        limit_cm=float(_get(chg_t, "limit_cm", num, "change")),
        cmap=_get(chg_t, "cmap", str, "change"),
        fallback_cmap=_get(chg_t, "fallback_cmap", str, "change"),
    )
    if change.limit_cm <= 0:
        raise ConfigError("[change] limit_cm must be > 0")

    cities: list[City] = []
    for i, c in enumerate(raw.get("cities", [])):
        if not isinstance(c, dict):
            raise ConfigError(f"[[cities]] entry {i} is not a table")
        align = str(c.get("align", "left"))
        if align not in ("left", "right"):
            raise ConfigError(f"[[cities]] '{c.get('name')}': align must be 'left' or 'right'")
        cities.append(
            City(
                name=_get(c, "name", str, "cities"),
                lon=float(_get(c, "lon", num, "cities")),
                lat=float(_get(c, "lat", num, "cities")),
                align=align,
            )
        )

    display = DisplayConfig(
        enabled=_get(disp_t, "enabled", bool, "display"),
        reload_s=_get(disp_t, "reload_s", int, "display"),
        slideshow_delay_s=_get(disp_t, "slideshow_delay_s", int, "display"),
    )

    interval = _get(sched, "interval_hours", int, "schedule")
    if not 1 <= interval <= 24:
        raise ConfigError("[schedule] interval_hours must be between 1 and 24")
    keep_days = _get(paths, "keep_days", int, "paths")
    if keep_days < 2:
        raise ConfigError("[paths] keep_days must be >= 2")

    return Config(
        path=cfg_path,
        output_dir=_resolve(base, _get(paths, "output_dir", str, "paths")),
        cache_dir=_resolve(base, _get(paths, "cache_dir", str, "paths")),
        natural_earth_dir=_resolve(base, _get(paths, "natural_earth_dir", str, "paths")),
        keep_days=keep_days,
        interval_hours=interval,
        api=api,
        image=image,
        depth=depth,
        change=change,
        cities=cities,
        display=display,
        fingerprint=hashlib.sha256(data).hexdigest()[:16],
    )
