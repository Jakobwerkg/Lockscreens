"""Render the snow depth and 24 h change maps as display-ready PNGs.

The data is drawn on its native grid: ``ccrs.epsg(3416)`` (ETRS89 / Austria
Lambert) is both the map projection and the data transform, so cartopy does
not reproject the raster. Natural Earth overlays (lon/lat) are projected onto
it instead.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: must be set before pyplot is imported

import cartopy.crs as ccrs  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from cartopy.feature import ShapelyFeature  # noqa: E402
from cartopy.io import shapereader  # noqa: E402

from snowgrid.config import Config  # noqa: E402
from snowgrid.fetch import SnowPair  # noqa: E402
from snowgrid.naturalearth import layer_path, use_local_data  # noqa: E402

log = logging.getLogger(__name__)

FOOTER = "Data: GeoSphere Austria, SNOWGRID v2.1, CC BY 4.0"
MAP_MARGIN_M = 6000.0  # padding around the data grid, metres


# ── projection ───────────────────────────────────────────────────────────────
def austria_lambert(extent: tuple[float, float, float, float]) -> ccrs.Projection:
    """Return ``ccrs.epsg(3416)`` with bounds wide enough for the data grid.

    cartopy derives an EPSG projection's bounds from the four corners of its
    lon/lat area of use. On a conic projection the edges of that box bulge
    outwards between the corners, so the derived box is too small: it would
    cut ~25 km off the south of the SNOWGRID grid (and with it the southern
    tip of Carinthia). Widening the bounds to cover the grid fixes that
    without changing the projection itself.
    """
    proj = ccrs.epsg(3416)
    x0, x1, y0, y1 = extent
    m = 2 * MAP_MARGIN_M
    bx0, bx1, by0, by1 = proj.bounds
    proj.bounds = (min(bx0, x0 - m), max(bx1, x1 + m), min(by0, y0 - m), max(by1, y1 + m))
    return proj


def _lonlat_bbox(proj: ccrs.Projection, extent: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Lon/lat bounding box ``(west, south, east, north)`` of a projected extent."""
    x0, x1, y0, y1 = extent
    xs = np.concatenate([np.linspace(x0, x1, 50), np.full(50, x1), np.linspace(x1, x0, 50), np.full(50, x0)])
    ys = np.concatenate([np.full(50, y0), np.linspace(y0, y1, 50), np.full(50, y1), np.linspace(y1, y0, 50)])
    pts = ccrs.PlateCarree().transform_points(proj, xs, ys)
    return (
        float(pts[:, 0].min()) - 0.2,
        float(pts[:, 1].min()) - 0.2,
        float(pts[:, 0].max()) + 0.2,
        float(pts[:, 1].max()) + 0.2,
    )


# ── overlays ─────────────────────────────────────────────────────────────────
@dataclass
class Overlays:
    """Natural Earth geometries clipped to the map area, loaded once per run."""

    borders: list = field(default_factory=list)
    states: list = field(default_factory=list)
    rivers: list = field(default_factory=list)
    lakes: list = field(default_factory=list)


def _read(key: str, bbox: tuple[float, float, float, float]) -> list[shapereader.Record]:
    """Records of Natural Earth layer ``key`` that intersect ``bbox``."""
    path = str(layer_path(key))
    try:
        return list(shapereader.Reader(path, bbox=bbox).records())
    except TypeError:  # older cartopy without the bbox argument
        w, s, e, n = bbox
        out = []
        for r in shapereader.Reader(path).records():
            if r.geometry is None:
                continue
            x0, y0, x1, y1 = r.geometry.bounds
            if x0 <= e and x1 >= w and y0 <= n and y1 >= s:
                out.append(r)
        return out


def load_overlays(cfg: Config, proj: ccrs.Projection, extent: tuple[float, float, float, float]) -> Overlays:
    """Read every overlay layer from the local Natural Earth directory.

    Bundesländer come from the admin_1 polygons filtered to Austria, so
    provinces of neighbouring countries are not drawn.
    """
    use_local_data(cfg.natural_earth_dir)
    bbox = _lonlat_bbox(proj, extent)
    ov = Overlays()
    ov.borders = [r.geometry for r in _read("borders", bbox)]
    ov.states = [
        r.geometry for r in _read("states", bbox)
        if str(r.attributes.get("adm0_a3", r.attributes.get("ADM0_A3", ""))).upper() == "AUT"
    ]
    ov.rivers = [r.geometry for r in _read("rivers", bbox)]  # major rivers only
    ov.lakes = [r.geometry for r in _read("lakes", bbox) + _read("lakes_europe", bbox)]
    if not ov.states:
        log.warning("no Austrian admin_1 polygons found in Natural Earth data")
    return ov


# ── figure scaffolding ───────────────────────────────────────────────────────
@dataclass
class Frame:
    """A figure with a map axes and helpers sized for the configured output."""

    fig: plt.Figure
    ax: plt.Axes
    scale: float  # multiply point sizes (fonts, line widths) by this
    px: float     # one layout "pixel" at the 1920x1080 reference, as real pixels

    def fx(self, pixels: float) -> float:
        """Horizontal reference pixels as a figure fraction."""
        return pixels * self.px / (self.fig.get_figwidth() * self.fig.dpi)

    def fy(self, pixels: float) -> float:
        """Vertical reference pixels as a figure fraction."""
        return pixels * self.px / (self.fig.get_figheight() * self.fig.dpi)


# Layout at the 1920x1080 reference size, in pixels; scaled for other sizes.
HEADER_PX = 165   # title + subtitle band
FOOTER_PX = 55    # credit line
COLORBAR_PX = 200  # space right of the map for the colorbar and its labels
SIDE_PX = 25


def _new_frame(cfg: Config, proj: ccrs.Projection, extent: tuple[float, float, float, float], ov: Overlays) -> Frame:
    """Create a dark figure with the map axes and the Austria land fill.

    Header, footer and colorbar get fixed bands (scaled with the image size),
    and the map fills the rest, so any aspect ratio works.
    """
    img = cfg.image
    px = min(img.width / 1920, img.height / 1080)
    fig = plt.figure(figsize=(img.width / img.dpi, img.height / img.dpi), dpi=img.dpi, facecolor=img.background)
    frame = Frame(fig=fig, ax=None, scale=px * 100 / img.dpi, px=px)  # type: ignore[arg-type]
    left, bottom = frame.fx(SIDE_PX), frame.fy(FOOTER_PX)
    rect = (left, bottom, 1 - left - frame.fx(COLORBAR_PX), 1 - bottom - frame.fy(HEADER_PX))
    ax = fig.add_axes(rect, projection=proj)
    frame.ax = ax
    ax.set_facecolor(img.background)
    ax.spines["geo"].set_visible(False)
    x0, x1, y0, y1 = extent
    ax.set_extent((x0 - MAP_MARGIN_M, x1 + MAP_MARGIN_M, y0 - MAP_MARGIN_M, y1 + MAP_MARGIN_M), crs=proj)

    pc = ccrs.PlateCarree()
    if ov.states:
        # Austria's land in a slightly lighter tone so "no snow" (transparent)
        # is distinguishable from "outside Austria".
        ax.add_feature(ShapelyFeature(ov.states, pc), facecolor=img.land, edgecolor="none", zorder=0)
    return frame


def _draw_overlays(frame: Frame, cfg: Config, proj: ccrs.Projection, ov: Overlays) -> None:
    """Draw water, borders, Bundesländer and city labels above the raster."""
    ax, s, img = frame.ax, frame.scale, cfg.image
    pc = ccrs.PlateCarree()
    if ov.lakes:
        ax.add_feature(ShapelyFeature(ov.lakes, pc), facecolor=img.water, edgecolor=img.water,
                       linewidth=0.4 * s, zorder=3)
    if ov.rivers:
        # Below the raster (zorder 1): rivers show in snow-free valleys and
        # lowlands but never hide or mimic snow-depth colours.
        ax.add_feature(ShapelyFeature(ov.rivers, pc), facecolor="none", edgecolor=img.water,
                       linewidth=1.3 * s, zorder=1)
    if ov.states:
        ax.add_feature(ShapelyFeature(ov.states, pc), facecolor="none", edgecolor=img.state_border,
                       linewidth=0.9 * s, zorder=4)
    if ov.borders:
        ax.add_feature(ShapelyFeature(ov.borders, pc), facecolor="none", edgecolor=img.border,
                       linewidth=1.8 * s, zorder=5)

    halo = [pe.withStroke(linewidth=3.5 * s, foreground=img.background)]
    for city in cfg.cities:
        x, y = proj.transform_point(city.lon, city.lat, pc)
        ax.plot(x, y, marker="o", markersize=7 * s, color=img.foreground,
                markeredgecolor=img.background, markeredgewidth=1.2 * s, zorder=6)
        dx = 9 if city.align == "left" else -9
        ax.annotate(
            city.name, xy=(x, y), xytext=(dx * s, 5 * s), textcoords="offset points",
            ha=city.align, va="bottom", fontsize=17 * s, color=img.foreground,
            fontweight="bold", path_effects=halo, zorder=7,
        )


def _decorate(frame: Frame, cfg: Config, title: str, subtitle: str) -> None:
    """Add title, subtitle, data credit and generation time."""
    fig, s, img = frame.fig, frame.scale, cfg.image
    x0, x1 = frame.fx(55), 1 - frame.fx(55)
    fig.text(x0, 1 - frame.fy(40), title, ha="left", va="top", fontsize=34 * s, fontweight="bold",
             color=img.foreground)
    fig.text(x0, 1 - frame.fy(108), subtitle, ha="left", va="top", fontsize=19 * s, color=img.foreground,
             alpha=0.8)
    fig.text(x0, frame.fy(25), FOOTER, ha="left", va="bottom", fontsize=14 * s, color=img.foreground,
             alpha=0.7)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fig.text(x1, frame.fy(25), f"rendered {now}", ha="right", va="bottom", fontsize=14 * s,
             color=img.foreground, alpha=0.5)


def _colorbar_axes(frame: Frame) -> plt.Axes:
    """Axes for a vertical colorbar just right of the (aspect-corrected) map."""
    frame.ax.apply_aspect()
    pos = frame.ax.get_position()
    # The map ends at most COLORBAR_PX before the right edge, so this always fits.
    return frame.fig.add_axes((pos.x1 + frame.fx(30), pos.y0 + 0.08 * pos.height, frame.fx(34), 0.84 * pos.height))


def _style_colorbar(cbar, frame: Frame, cfg: Config, label: str) -> None:
    """Apply the dark-theme style to a colorbar."""
    s, fg = frame.scale, cfg.image.foreground
    cbar.set_label(label, color=fg, fontsize=19 * s, labelpad=12 * s)
    cbar.ax.tick_params(colors=fg, labelsize=16 * s, length=5 * s, width=1.0 * s)
    cbar.outline.set_edgecolor(fg)
    cbar.outline.set_linewidth(0.8 * s)


def _imshow(frame: Frame, proj: ccrs.Projection, data: np.ndarray, extent: tuple[float, float, float, float],
            cmap: mcolors.Colormap, norm: mcolors.Normalize):
    """Draw ``data`` (row 0 = south) on its native grid without reprojection."""
    return frame.ax.imshow(
        data, origin="lower", extent=extent, transform=proj, cmap=cmap, norm=norm,
        interpolation="nearest", zorder=2,
    )


# ── colour scales ────────────────────────────────────────────────────────────
def depth_scale(cfg: Config) -> tuple[mcolors.Colormap, mcolors.BoundaryNorm]:
    """Discrete colormap/norm for depth classes; values above the top level use the last colour."""
    levels, colors = cfg.depth.levels, cfg.depth.colors
    cmap = mcolors.ListedColormap(colors[:-1], name="snow_depth").with_extremes(
        over=colors[-1], under=(0, 0, 0, 0), bad=(0, 0, 0, 0)
    )
    # Without `extend`, values >= the top level map to index N, i.e. the cmap's
    # "over" colour; the colorbar's extend="max" arrow shows that class.
    norm = mcolors.BoundaryNorm(levels, ncolors=cmap.N)
    return cmap, norm


def change_scale(cfg: Config) -> tuple[mcolors.Colormap, mcolors.Normalize]:
    """Diverging colormap centred on 0 with fixed limits +-``limit_cm``."""
    try:
        base = matplotlib.colormaps[cfg.change.cmap]
    except KeyError:
        log.warning("colormap '%s' not available, using '%s'", cfg.change.cmap, cfg.change.fallback_cmap)
        base = matplotlib.colormaps[cfg.change.fallback_cmap]
    cmap = base.with_extremes(bad=(0, 0, 0, 0))
    lim = cfg.change.limit_cm
    return cmap, mcolors.TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)


# ── statistics for subtitles / logs ──────────────────────────────────────────
@dataclass(frozen=True)
class Stats:
    """Summary numbers for one rendered day."""

    max_depth_cm: float
    snow_cover_pct: float
    max_gain_cm: float
    max_loss_cm: float
    valid_cells: int


def compute_stats(pair: SnowPair, cfg: Config) -> Stats:
    """Domain statistics used in subtitles and log output."""
    valid = np.isfinite(pair.latest_cm)
    n = int(valid.sum())
    snowy = valid & (pair.latest_cm >= cfg.depth.no_snow_threshold_cm)
    change = pair.change_cm
    finite_change = change[np.isfinite(change)]
    return Stats(
        max_depth_cm=float(np.nanmax(pair.latest_cm)),
        snow_cover_pct=100.0 * snowy.sum() / n if n else 0.0,
        max_gain_cm=float(finite_change.max()) if finite_change.size else 0.0,
        max_loss_cm=float(finite_change.min()) if finite_change.size else 0.0,
        valid_cells=n,
    )


def _fmt_day(d: date, year: bool = True) -> str:
    """``Sat 21 Nov 2026`` (or ``Sat 21 Nov`` with ``year=False``); locale-independent."""
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    text = f"{days[d.weekday()]} {d.day} {months[d.month - 1]}"
    return f"{text} {d.year}" if year else text


# ── the two maps ─────────────────────────────────────────────────────────────
def render_depth(pair: SnowPair, cfg: Config, proj: ccrs.Projection, ov: Overlays, stats: Stats) -> plt.Figure:
    """Snow depth [cm] for ``pair.day``; cells without snow are transparent."""
    data = np.where(pair.latest_cm >= cfg.depth.no_snow_threshold_cm, pair.latest_cm, np.nan)
    cmap, norm = depth_scale(cfg)
    frame = _new_frame(cfg, proj, pair.extent, ov)
    im = _imshow(frame, proj, data, pair.extent, cmap, norm)
    _draw_overlays(frame, cfg, proj, ov)

    cax = _colorbar_axes(frame)
    cbar = frame.fig.colorbar(im, cax=cax, extend="max", spacing="uniform", ticks=cfg.depth.levels,
                              extendfrac=0.08)
    cbar.ax.set_yticklabels([f"{v:g}" for v in cfg.depth.levels])
    _style_colorbar(cbar, frame, cfg, "Snow depth [cm]")
    top = cfg.depth.levels[-1]
    cbar.ax.text(1.0, 1.04, f"  {top:g}+", transform=cbar.ax.transAxes, ha="left", va="center",
                 fontsize=16 * frame.scale, color=cfg.image.foreground)

    _decorate(
        frame, cfg,
        f"Snow depth  ·  {_fmt_day(pair.day)}  (UTC)",
        f"Max {stats.max_depth_cm:.0f} cm  ·  snow cover {stats.snow_cover_pct:.0f} % of Austria  ·  "
        f"no colour = no snow (< {cfg.depth.no_snow_threshold_cm:g} cm)",
    )
    return frame.fig


def render_change(pair: SnowPair, cfg: Config, proj: ccrs.Projection, ov: Overlays, stats: Stats) -> plt.Figure:
    """24 h change [cm] = ``day`` - ``day - 1``; transparent where there was no snow on either day."""
    thr = cfg.depth.no_snow_threshold_cm
    change = pair.change_cm
    no_snow_both = (pair.latest_cm < thr) & (pair.previous_cm < thr)
    data = np.where(no_snow_both, np.nan, change)
    cmap, norm = change_scale(cfg)
    frame = _new_frame(cfg, proj, pair.extent, ov)
    im = _imshow(frame, proj, data, pair.extent, cmap, norm)
    _draw_overlays(frame, cfg, proj, ov)

    lim = cfg.change.limit_cm
    cax = _colorbar_axes(frame)
    ticks = np.linspace(-lim, lim, 7)
    cbar = frame.fig.colorbar(im, cax=cax, extend="both", ticks=ticks, extendfrac=0.06)
    cbar.ax.set_yticklabels([f"{t:+g}" if t else "0" for t in ticks])
    _style_colorbar(cbar, frame, cfg, "24 h change in snow depth [cm]")

    prev = pair.day - timedelta(days=1)
    _decorate(
        frame, cfg,
        f"24 h change  ·  {_fmt_day(prev, year=False)} → {_fmt_day(pair.day)}  (UTC)",
        f"Largest gain {stats.max_gain_cm:+.0f} cm  ·  largest loss {stats.max_loss_cm:+.0f} cm  ·  "
        f"no colour = no snow on either day",
    )
    return frame.fig


# ── atomic output ────────────────────────────────────────────────────────────
def save_png_atomic(fig: plt.Figure, dest: Path, dpi: int) -> Path:
    """Render ``fig`` to a temp file next to ``dest`` and return the temp path.

    The caller moves it into place with :func:`commit`, so viewers never see a
    half-written PNG and both maps can be swapped in together.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.stem}.", suffix=".png.tmp", dir=dest.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fig.savefig(fh, format="png", dpi=dpi, facecolor=fig.get_facecolor())
            fh.flush()
            os.fsync(fh.fileno())
        tmp.chmod(0o644)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        plt.close(fig)
    return tmp


def commit(tmp: Path, dest: Path) -> None:
    """Atomically move ``tmp`` to ``dest`` (same filesystem, so ``os.replace`` is atomic)."""
    os.replace(tmp, dest)
    try:  # make the rename itself durable
        dfd = os.open(dest.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def render_all(pair: SnowPair, cfg: Config) -> dict[str, Path]:
    """Render both maps to temp files in ``cfg.output_dir``.

    Returns a mapping ``{"snow_depth": tmp_path, "snow_change_24h": tmp_path}``.
    Nothing visible is touched until the caller commits the files.
    """
    proj = austria_lambert(pair.extent)
    ov = load_overlays(cfg, proj, pair.extent)
    stats = compute_stats(pair, cfg)
    tmps: dict[str, Path] = {}
    try:
        tmps["snow_depth"] = save_png_atomic(
            render_depth(pair, cfg, proj, ov, stats), cfg.output_dir / "snow_depth.png", cfg.image.dpi
        )
        tmps["snow_change_24h"] = save_png_atomic(
            render_change(pair, cfg, proj, ov, stats), cfg.output_dir / "snow_change_24h.png", cfg.image.dpi
        )
    except BaseException:
        for t in tmps.values():
            t.unlink(missing_ok=True)
        plt.close("all")
        raise
    return tmps
