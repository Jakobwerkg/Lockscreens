"""
Renders the 7-day SPARTACUS anomaly dashboard to a PNG.

Five maps (mean / min / max temperature, precipitation, sunshine) plus a
summary card, on a dark layout sized to the target screen.
"""

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch

from spartacus_data import PARAM_INFO

BORDERS_FILE = Path(__file__).parent / "borders.npz"

# ── palette ──────────────────────────────────────────────────────────────────
BG          = "#0b0f16"
CARD        = "#151c27"
CARD_EDGE   = "#232d3d"
FG          = "#e8eef6"
MUTED       = "#8797ac"
FAINT       = "#4a5769"
WARM        = "#ff8a65"
COOL        = "#5eb3f6"

# blue-grey (dull) → gold (bright) for sunshine anomalies
SUN_CMAP = LinearSegmentedColormap.from_list(
    "sun", ["#2b4a6b", "#4a7ba7", "#8fb4d0", "#dfe6ec",
            "#f7f4ea", "#f2d98b", "#e8b13c", "#cf8615", "#9b5c05"])

BORDER_AT = "#dbe4ef"       # Austrian national border
BORDER_NB = "#5a6b82"       # borders between the neighbouring countries

TEMP_LEVELS = [-8, -6, -4, -3, -2, -1, -0.5, 0.5, 1, 2, 3, 4, 6, 8]
SUN_LEVELS  = [-6, -5, -4, -3, -2, -1, -0.5, 0.5, 1, 2, 3, 4, 5, 6]
RAIN_LEVELS = [-100, -75, -50, -25, -10, 10, 25, 50, 100, 200]

# colours for the "Austria mean" badge: (below normal, above normal)
BADGE = {
    "TM24": (COOL, WARM), "TN": (COOL, WARM), "TX": (COOL, WARM),
    "RR":   ("#c39a52", "#4db6ac"),      # dry ↔ wet, matching BrBG
    "SA":   ("#7fa8cd", "#e8b13c"),      # dull ↔ sunny
}

# panel order: (parameter, colormap, levels, colorbar label, extend)
PANELS = [
    ("TM24", "RdBu_r",  TEMP_LEVELS, "anomaly  (K)",            "both"),
    ("TN",   "RdBu_r",  TEMP_LEVELS, "anomaly  (K)",            "both"),
    ("TX",   "RdBu_r",  TEMP_LEVELS, "anomaly  (K)",            "both"),
    ("RR",   "BrBG",    RAIN_LEVELS, "anomaly  (% of normal)",  "max"),
    ("SA",   SUN_CMAP,  SUN_LEVELS,  "anomaly  (hours/day)",    "both"),
]


# ── EPSG:3416 – ETRS89 / Austria Lambert (LCC 2SP on GRS80) ──────────────────
_A  = 6378137.0
_E  = math.sqrt(2 / 298.257222101 - (1 / 298.257222101) ** 2)
_P1, _P2 = math.radians(49.0), math.radians(46.0)
_P0, _L0 = math.radians(47.5), math.radians(13.0 + 1.0 / 3.0)
_FE = _FN = 400000.0


def _lcc_t(phi):
    s = _E * np.sin(phi)
    return np.tan(np.pi / 4 - phi / 2) / ((1 - s) / (1 + s)) ** (_E / 2)


def _lcc_m(phi):
    return np.cos(phi) / np.sqrt(1 - (_E * np.sin(phi)) ** 2)


_NN = ((np.log(_lcc_m(_P1)) - np.log(_lcc_m(_P2)))
       / (np.log(_lcc_t(_P1)) - np.log(_lcc_t(_P2))))
_FF = _lcc_m(_P1) / (_NN * _lcc_t(_P1) ** _NN)
_R0 = _A * _FF * _lcc_t(_P0) ** _NN


def lonlat_to_xy(lon, lat):
    """WGS84/ETRS89 degrees → (easting, northing) in metres, EPSG:3416."""
    phi = np.radians(np.asarray(lat, dtype="float64"))
    lam = np.radians(np.asarray(lon, dtype="float64"))
    r = _A * _FF * _lcc_t(phi) ** _NN
    theta = _NN * (lam - _L0)
    return _FE + r * np.sin(theta), _FN + _R0 - r * np.cos(theta)


def load_borders(coords):
    """Vendored national borders, converted to the grid's index space.

    Returns (austria_segments, neighbour_segments); each segment is an
    (n, 2) array of column/row positions usable straight in imshow space.
    """
    if not BORDERS_FILE.exists():
        return [], []
    east, north = coords["easting"], coords["northing"]
    res = float(east[1] - east[0])

    austria, others = [], []
    with np.load(BORDERS_FILE) as z:
        for key in z.files:
            seg = z[key]
            x, y = lonlat_to_xy(seg[:, 0], seg[:, 1])
            idx = np.column_stack([(x - east[0]) / res, (y - north[0]) / res])
            (austria if key.startswith("at_") else others).append(idx)
    return austria, others


def _draw_borders(ax, austria, others):
    for seg in others:
        ax.plot(seg[:, 0], seg[:, 1], color=BORDER_NB, linewidth=0.6,
                alpha=0.75, solid_capstyle="round", zorder=3)
    for seg in austria:
        ax.plot(seg[:, 0], seg[:, 1], color=BORDER_AT, linewidth=1.1,
                alpha=0.95, solid_capstyle="round", zorder=4)


def _discrete(cmap, levels):
    cmap = plt.get_cmap(cmap) if isinstance(cmap, str) else cmap
    colors = cmap(np.linspace(0.02, 0.98, len(levels) - 1))
    cm = matplotlib.colors.ListedColormap(colors)
    cm.set_bad(alpha=0.0)
    cm.set_over(cmap(1.0))
    cm.set_under(cmap(0.0))
    return cm, BoundaryNorm(levels, cm.N)


def _fit(box, data_aspect, fig_aspect):
    """Shrink a figure-fraction box to exactly hold an image of `data_aspect`."""
    x0, y0, bw, bh = box
    fw, fh = bw, bw * fig_aspect / data_aspect
    if fh > bh:
        fh, fw = bh, bh * data_aspect / fig_aspect
    return [x0 + (bw - fw) / 2, y0 + (bh - fh) / 2, fw, fh]


def _card(fig, box, radius=0.012):
    # zorder below the map axes, which are lifted to 1 in render()
    fig.add_artist(FancyBboxPatch(
        (box[0], box[1]), box[2], box[3],
        boxstyle=f"round,pad=0,rounding_size={radius}",
        transform=fig.transFigure, facecolor=CARD, edgecolor=CARD_EDGE,
        linewidth=1.0, zorder=-1))


def _area_mean(values):
    """Plain mean over the grid – SPARTACUS cells are all 1 km × 1 km."""
    v = np.asarray(values, dtype="float64")
    return float(np.nanmean(v)) if np.isfinite(v).any() else float("nan")


def _headline(param, field):
    """National mean anomaly → (value, long label, short label, colour)."""
    if param == "RR":
        obs, clim = _area_mean(field["observed"]), _area_mean(field["climate"])
        value = signed = 100.0 * (obs / clim - 1.0) if clim > 0 else float("nan")
        long = short = f"{value:+.0f}%"
    else:
        value = signed = _area_mean(field["difference"])
        unit = "h/day" if param == "SA" else "K"
        long = short = f"{value:+.1f} {unit}"
    low, high = BADGE[param]
    colour = high if signed > 0 else low if signed < 0 else MUTED
    return value, long, short, colour


def render(report, out_path, width=1920, height=1080, dpi=100):
    fields  = report["fields"]
    dates   = report["dates"]
    fig_asp = width / height
    n_rows, n_cols = fields["TX"]["anomaly"].shape
    data_asp = n_cols / n_rows
    borders = load_borders(report["coords"])

    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG)

    # ── header ───────────────────────────────────────────────────────────────
    period = (f"{dates[0]:%-d %b} – {dates[-1]:%-d %b %Y}" if dates[0].year == dates[-1].year
              else f"{dates[0]:%-d %b %Y} – {dates[-1]:%-d %b %Y}")
    fig.text(0.018, 0.945, "Austria · 7-day climate anomaly", color=FG,
             fontsize=30, fontweight="bold", va="center", ha="left")
    fig.text(0.018, 0.902, f"{len(dates)}-day mean vs. the 1991–2020 normal for the "
                           f"same calendar days   ·   SPARTACUS v3, 1 km grid",
             color=MUTED, fontsize=13.5, va="center", ha="left")
    fig.text(0.982, 0.945, period, color=FG, fontsize=19,
             va="center", ha="right", fontweight="bold")
    fig.text(0.982, 0.903, f"updated {report['generated']:%a %-d %b %Y, %H:%M}",
             color=MUTED, fontsize=12, va="center", ha="right")
    fig.add_artist(plt.Line2D([0.018, 0.982], [0.876, 0.876], transform=fig.transFigure,
                              color=CARD_EDGE, linewidth=1.0))

    # ── panel grid (3 × 2, last cell = summary) ──────────────────────────────
    left, right, top, bottom = 0.014, 0.986, 0.862, 0.036
    cols, rows = 3, 2
    cw = (right - left) / cols
    ch = (top - bottom) / rows
    pad = 0.008

    for idx, (param, cmap_name, levels, cbar_label, extend) in enumerate(PANELS):
        r, c = divmod(idx, cols)
        cell = [left + c * cw + pad, top - (r + 1) * ch + pad,
                cw - 2 * pad, ch - 2 * pad]
        _card(fig, cell)

        info = PARAM_INFO[param]
        field = fields[param]
        _, badge_txt, _, badge_col = _headline(param, field)

        # titles
        fig.text(cell[0] + 0.011, cell[1] + cell[3] - 0.030, info["label"],
                 color=FG, fontsize=17, fontweight="bold", va="center", ha="left")
        fig.text(cell[0] + 0.011, cell[1] + cell[3] - 0.058,
                 f"{param} · {info['long']}", color=MUTED, fontsize=10.5,
                 va="center", ha="left")
        fig.text(cell[0] + cell[2] - 0.011, cell[1] + cell[3] - 0.036, badge_txt,
                 color=badge_col, fontsize=16, fontweight="bold",
                 va="center", ha="right")
        fig.text(cell[0] + cell[2] - 0.011, cell[1] + cell[3] - 0.062,
                 "Austria mean", color=FAINT, fontsize=9.5, va="center", ha="right")

        # map
        map_box = [cell[0] + 0.008, cell[1] + 0.068,
                   cell[2] - 0.016, cell[3] - 0.068 - 0.076]
        ax = fig.add_axes(_fit(map_box, data_asp, fig_asp), zorder=1)
        ax.set_facecolor("none")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

        cmap, norm = _discrete(cmap_name, levels)
        im = ax.imshow(np.ma.masked_invalid(field["anomaly"]), origin="lower",
                       cmap=cmap, norm=norm, interpolation="nearest")

        _draw_borders(ax, *borders)
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(-0.5, n_rows - 0.5)

        # colour bar – label every boundary except the narrow "near normal" pair
        cb_ax = fig.add_axes([cell[0] + 0.034, cell[1] + 0.042,
                              cell[2] - 0.068, 0.016], zorder=1)
        ticks = [v for v in levels if abs(v) != 0.5]
        cb = fig.colorbar(im, cax=cb_ax, orientation="horizontal",
                          extend=extend, spacing="uniform",
                          boundaries=levels, ticks=ticks)
        cb.outline.set_visible(False)
        cb.ax.tick_params(colors=MUTED, labelsize=9, length=0, pad=3)
        cb.set_ticklabels([f"{v:g}" for v in ticks])
        fig.text(cell[0] + cell[2] / 2, cell[1] + 0.016, cbar_label,
                 color=FAINT, fontsize=10, va="center", ha="center")

    # ── summary card ─────────────────────────────────────────────────────────
    r, c = divmod(len(PANELS), cols)
    cell = [left + c * cw + pad, top - (r + 1) * ch + pad, cw - 2 * pad, ch - 2 * pad]
    _card(fig, cell)

    x0    = cell[0] + 0.014
    x_end = cell[0] + cell[2] - 0.014
    fig.text(x0, cell[1] + cell[3] - 0.030, "Summary", color=FG, fontsize=17,
             fontweight="bold", va="center", ha="left")
    fig.text(x0, cell[1] + cell[3] - 0.055,
             f"Austria-wide averages, {len(dates)} days ending {dates[-1]:%-d %b %Y}",
             color=MUTED, fontsize=10.5, va="center", ha="left")

    # right-aligned value columns
    col = [x_end - 0.150, x_end - 0.082, x_end]
    y = cell[1] + cell[3] - 0.082
    for label, px in zip(("observed", "normal", "anomaly"), col):
        fig.text(px, y, label, color=FAINT, fontsize=10.5, va="center", ha="right")

    for param, *_ in PANELS:
        y -= 0.040
        info, field = PARAM_INFO[param], fields[param]
        _, _, short, colour = _headline(param, field)
        obs, clim = _area_mean(field["observed"]), _area_mean(field["climate"])

        fig.text(x0, y, info["label"], color=FG, fontsize=13, va="center", ha="left")
        fig.text(x0, y - 0.018, f"{param} · {info['unit']}", color=FAINT, fontsize=9,
                 va="center", ha="left")
        fig.text(col[0], y, f"{obs:.1f}",  color=FG,    fontsize=13, va="center", ha="right")
        fig.text(col[1], y, f"{clim:.1f}", color=MUTED, fontsize=13, va="center", ha="right")
        fig.text(col[2], y, short, color=colour, fontsize=13, fontweight="bold",
                 va="center", ha="right")
        fig.add_artist(plt.Line2D([x0, x_end], [y - 0.028, y - 0.028],
                                  transform=fig.transFigure,
                                  color=CARD_EDGE, linewidth=0.8))

    fig.text(x0, cell[1] + 0.063,
             f"Reference period 1991–2020 ({report['n_years']} years)",
             color=MUTED, fontsize=11, va="center", ha="left")
    fig.text(x0, cell[1] + 0.012,
             "Precipitation as percentage departure, all\nother fields as absolute difference.",
             color=FAINT, fontsize=9.5, va="bottom", ha="left", linespacing=1.5)

    # ── footer ───────────────────────────────────────────────────────────────
    fig.text(0.018, 0.016, "Data: GeoSphere Austria · SPARTACUS v3 (1 km, daily) · CC BY 4.0",
             color=FAINT, fontsize=10, va="center", ha="left")
    fig.text(0.982, 0.016, "data.hub.geosphere.at", color=FAINT, fontsize=10,
             va="center", ha="right")

    fig.savefig(out_path, facecolor=BG, dpi=dpi)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    from pathlib import Path
    from spartacus_data import build_report

    out = Path(__file__).parent / "cache" / "preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    render(build_report(), out)
    print(f"wrote {out}")
