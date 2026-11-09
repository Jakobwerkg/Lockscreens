#!/usr/bin/env python3
"""
generate_charts.py
Creates clean, professional multi-station charts in classic hydro monitoring style
(similar to eHYD / hydro.tirol.gv.at plots).

Designed to show multiple stations on one PNG.
"""

from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib import rcParams

from data_updater import DataUpdater

GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(exist_ok=True)

# Dark professional theme
plt.style.use("dark_background")
rcParams["font.family"] = "DejaVu Sans"
rcParams["font.size"] = 10
rcParams["axes.labelsize"] = 11
rcParams["axes.titlesize"] = 13
rcParams["figure.facecolor"] = "#0d1117"
rcParams["axes.facecolor"] = "#161b22"
rcParams["savefig.facecolor"] = "#0d1117"
rcParams["grid.color"] = "#30363d"
rcParams["axes.edgecolor"] = "#30363d"


def create_multi_station_overview(
    current: dict,
    title: str,
    filename: str,
    max_stations: int = 8,
    highlight_hzbnr: list = None
) -> Path:
    """
    Create a clean multi-station overview chart.
    Shows current value + station name in a professional layout.
    """
    if not current:
        return None

    # Sort by station name for consistency
    items = sorted(current.items(), key=lambda x: x[1].get("name", x[0]))

    if len(items) > max_stations:
        items = items[:max_stations]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)

    names = []
    values = []
    units = []
    colors = []

    highlight_set = set(highlight_hzbnr or [])

    for hz, data in items:
        name = data.get("name", hz)[:28]
        val = data.get("wert")
        unit = data.get("einheit", "")

        if val is None:
            continue

        names.append(name)
        values.append(val)
        units.append(unit)

        if hz in highlight_set:
            colors.append("#58a6ff")  # highlight color
        else:
            colors.append("#3fb950")

    if not values:
        plt.close(fig)
        return None

    y_pos = range(len(names))
    bars = ax.barh(y_pos, values, color=colors, edgecolor="#30363d", height=0.65)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10)
    ax.invert_yaxis()

    ax.set_xlabel(f"Current Value ({units[0] if units else ''})", color="#c9d1d9")
    ax.set_title(title, color="#c9d1d9", fontsize=15, pad=15, fontweight="bold")

    # Add value labels on bars
    for bar, val, unit in zip(bars, values, units):
        width = bar.get_width()
        label = f"{val:.1f} {unit}"
        ax.text(width + max(values) * 0.015, bar.get_y() + bar.get_height()/2,
                label, va="center", ha="left", color="#c9d1d9", fontsize=10)

    ax.tick_params(colors="#c9d1d9")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Add timestamp
    ax.text(0.99, 0.01, datetime.now().strftime("%Y-%m-%d %H:%M"),
            transform=ax.transAxes, ha="right", va="bottom",
            color="#8b949e", fontsize=9)

    plt.tight_layout()
    out_path = GENERATED_DIR / filename
    plt.savefig(out_path, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)

    print(f"[generate_charts] Saved {out_path}")
    return out_path


def generate_all_charts(updater: DataUpdater = None):
    if updater is None:
        updater = DataUpdater()
        updater.update_current()

    current = updater.get_all_current()
    if not current:
        print("[generate_charts] No current data available")
        return []

    created = []

    # 1. Inn focus (highlight core Inn stations)
    inn_core = [hz for hz in current.keys() if hz in [
        "201525", "201673", "201475", "201806", "201905", "201319", "201293"
    ]]
    created.append(create_multi_station_overview(
        current,
        "Inn – Wichtige Pegel (Current)",
        "inn_multi.png",
        max_stations=10,
        highlight_hzbnr=inn_core
    ))

    # 2. Donau + Drau
    created.append(create_multi_station_overview(
        current,
        "Donau & Drau – Wichtige Pegel",
        "donau_drau_multi.png",
        max_stations=8
    ))

    # 3. Core Precipitation stations
    created.append(create_multi_station_overview(
        current,
        "Niederschlag – Core Stationen (nah an Hauptpegeln)",
        "precip_core_multi.png",
        max_stations=10
    ))

    return [p for p in created if p]


if __name__ == "__main__":
    print("=== Generating new style multi-station charts ===")
    paths = generate_all_charts()
    print(f"\nGenerated {len(paths)} charts:")
    for p in paths:
        print(f"  - {p.name}")
