"""Offline Natural Earth data for the map overlays.

``install.sh`` runs ``python -m snowgrid.naturalearth --config config.toml`` once
to download every shapefile the maps need into ``paths.natural_earth_dir``.
At render time :func:`use_local_data` points cartopy at that directory, so no
network access is needed for plotting.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cartopy
from cartopy.io import shapereader

from snowgrid.config import ConfigError, load_config

log = logging.getLogger(__name__)

# (resolution, category, name) of every Natural Earth layer used by plot.py.
LAYERS: dict[str, tuple[str, str, str]] = {
    "borders": ("10m", "cultural", "admin_0_boundary_lines_land"),
    "states": ("10m", "cultural", "admin_1_states_provinces"),
    "rivers": ("10m", "physical", "rivers_lake_centerlines"),
    "lakes": ("10m", "physical", "lakes"),
    "lakes_europe": ("10m", "physical", "lakes_europe"),
}


def use_local_data(data_dir: Path) -> None:
    """Make cartopy read (and, if ever needed, store) Natural Earth data in ``data_dir``."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cartopy.config["data_dir"] = str(data_dir)
    cartopy.config["pre_existing_data_dir"] = str(data_dir)


def layer_path(key: str) -> Path:
    """Local path of layer ``key``'s shapefile, downloading it if it is missing."""
    resolution, category, name = LAYERS[key]
    return Path(shapereader.natural_earth(resolution=resolution, category=category, name=name))


def prefetch(data_dir: Path) -> list[Path]:
    """Download every layer in :data:`LAYERS` into ``data_dir`` and return the paths."""
    use_local_data(data_dir)
    paths = []
    for key in LAYERS:
        p = layer_path(key)
        log.info("Natural Earth %-14s -> %s", key, p)
        paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: prefetch all layers for the configured directory."""
    ap = argparse.ArgumentParser(description="Download Natural Earth data for offline plotting.")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.toml"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s %(message)s")
    try:
        cfg = load_config(args.config)
        prefetch(cfg.natural_earth_dir)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    except Exception as exc:  # network/zip errors from cartopy's downloader
        log.error("Natural Earth download failed: %s", exc)
        return 1
    log.info("all Natural Earth layers available in %s", cfg.natural_earth_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
