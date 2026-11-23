"""Command-line entry point: fetch the latest SNOWGRID day and render both maps.

Usage::

    python -m snowgrid.main --once                 # one run (what the systemd timer does)
    python -m snowgrid.main --once --force         # re-download and re-render
    python -m snowgrid.main --once --date 2026-02-15
    python -m snowgrid.main                        # loop every schedule.interval_hours

A failed run logs the error, leaves the last good images untouched and exits
with status 1. Nothing half-written is ever left in the output directory.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import shutil
import sys
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

from snowgrid import __version__
from snowgrid.config import Config, ConfigError, load_config

log = logging.getLogger("snowgrid")

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
OUTPUT_NAMES = ("snow_depth", "snow_change_24h")
STATE_FILE = ".state.json"


class AlreadyRunning(RuntimeError):
    """Another instance holds the lock."""


# ── logging / locking ────────────────────────────────────────────────────────
def setup_logging(verbose: bool) -> None:
    """Log to stdout. Under systemd (journald adds timestamps) omit our own."""
    fmt = "%(levelname)s %(name)s: %(message)s"
    if not os.environ.get("JOURNAL_STREAM"):
        fmt = "%(asctime)s " + fmt
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, stream=sys.stdout, format=fmt,
                        datefmt="%Y-%m-%d %H:%M:%S", force=True)
    for noisy in ("urllib3", "matplotlib", "PIL", "fiona", "shapely"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def run_lock(cache_dir: Path) -> Iterator[None]:
    """Hold an exclusive, non-blocking lock so timer and manual runs never overlap."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / ".lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning(f"another snowgrid run holds {cache_dir / '.lock'}") from exc
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ── render state (skip re-rendering identical output) ────────────────────────
def read_state(cfg: Config) -> dict:
    """Last successfully published day and config fingerprint, or ``{}``."""
    try:
        return json.loads((cfg.output_dir / STATE_FILE).read_text())
    except (OSError, ValueError):
        return {}


def write_state(cfg: Config, day: date) -> None:
    """Atomically record which day and config the published images show."""
    p = cfg.output_dir / STATE_FILE
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"date": day.isoformat(), "config": cfg.fingerprint, "version": __version__}))
    os.replace(tmp, p)


def outputs_current(cfg: Config, day: date) -> bool:
    """True if the published images already show ``day`` with the current config."""
    state = read_state(cfg)
    return (
        state.get("date") == day.isoformat()
        and state.get("config") == cfg.fingerprint
        and state.get("version") == __version__
        and all((cfg.output_dir / f"{n}.png").is_file() for n in OUTPUT_NAMES)
    )


def prune_archive(cfg: Config, newest: date) -> None:
    """Delete dated PNG copies older than ``keep_days`` before ``newest``."""
    if not cfg.archive_dir.is_dir():
        return
    cutoff = newest - timedelta(days=cfg.keep_days - 1)
    for p in cfg.archive_dir.glob("*_????-??-??.png"):
        try:
            if date.fromisoformat(p.stem[-10:]) < cutoff:
                p.unlink()
                log.info("pruned archive/%s", p.name)
        except (ValueError, OSError) as exc:
            log.warning("could not prune %s: %s", p, exc)


def clean_stale_temps(cfg: Config) -> None:
    """Remove temp PNGs left behind by a run that was killed mid-render."""
    for d in (cfg.output_dir, cfg.archive_dir):
        if d.is_dir():
            for p in d.glob(".*.png.tmp"):
                p.unlink(missing_ok=True)


# ── one run ──────────────────────────────────────────────────────────────────
def run_once(cfg: Config, force: bool = False, day: date | None = None) -> None:
    """Fetch (if needed) and render one day.

    Args:
        cfg: application configuration.
        force: ignore the cache and the render state; download and render again.
        day: plot this day instead of the latest. Dated copies are always
            written; the fixed-name display images are only replaced when
            ``day`` is the latest available day.

    Raises:
        Exception: any failure; the published images are left unchanged.
    """
    # Imported here so --help and config errors stay fast on a Pi.
    from snowgrid import fetch, plot

    with run_lock(cfg.cache_dir):
        clean_stale_temps(cfg)
        session = fetch.make_session()
        meta: fetch.Metadata | None
        try:
            meta = fetch.get_metadata(session, cfg.api)
            log.info("dataset available %s … %s (%s, unit %s)", meta.start, meta.end, meta.crs, meta.unit)
        except fetch.FetchError:
            if day is None:
                raise
            meta = None
            log.warning("metadata unavailable, trying cache for %s", day)

        target = day or meta.end  # type: ignore[union-attr]
        is_latest = meta is not None and target == meta.end

        if is_latest and not force and outputs_current(cfg, target):
            log.info("images for %s are up to date, nothing to do", target)
            fetch.prune_cache(cfg.cache_dir, target, cfg.keep_days)
            return

        path = fetch.ensure_cached(session, cfg.api, meta, cfg.cache_dir, target, force=force)
        pair = fetch.load_pair(path, cfg.api.parameter, target, meta.unit if meta else "m")
        stats = plot.compute_stats(pair, cfg)
        log.info(
            "%s: max depth %.1f cm, snow cover %.1f %%, 24 h change %+.1f … %+.1f cm, %d valid cells",
            target, stats.max_depth_cm, stats.snow_cover_pct, stats.max_loss_cm, stats.max_gain_cm,
            stats.valid_cells,
        )

        t0 = time.monotonic()
        tmps = plot.render_all(pair, cfg)
        try:
            cfg.archive_dir.mkdir(parents=True, exist_ok=True)
            for name, tmp in tmps.items():
                dated = cfg.archive_dir / f"{name}_{target.isoformat()}.png"
                dated_tmp = dated.with_name(f".{dated.stem}.png.tmp")
                shutil.copyfile(tmp, dated_tmp)
                plot.commit(dated_tmp, dated)
            if is_latest:
                for name, tmp in tmps.items():
                    plot.commit(tmp, cfg.output_dir / f"{name}.png")
                write_state(cfg, target)
                log.info("published %s", ", ".join(f"{n}.png" for n in tmps))
            else:
                log.info("%s is not the latest day: wrote dated copies only", target)
        finally:
            for tmp in tmps.values():
                tmp.unlink(missing_ok=True)
        log.info("rendered in %.1f s -> %s", time.monotonic() - t0, cfg.output_dir)

        newest = meta.end if meta else target
        fetch.prune_cache(cfg.cache_dir, newest, cfg.keep_days, protect=path)
        prune_archive(cfg, newest)


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(
        prog="snowgrid",
        description="Render GeoSphere Austria SNOWGRID snow depth maps for a display.",
    )
    ap.add_argument("--once", action="store_true", help="run once and exit (used by the systemd timer)")
    ap.add_argument("--force", action="store_true", help="ignore the cache: download and render again")
    ap.add_argument("--date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="plot this day (UTC) instead of the latest; implies --once")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, metavar="PATH",
                    help=f"config file (default: {DEFAULT_CONFIG})")
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap.parse_args(argv)


def _attempt(cfg: Config, force: bool, day: date | None) -> int:
    """Run once, turning every failure into a logged error and an exit status."""
    try:
        run_once(cfg, force=force, day=day)
        return 0
    except AlreadyRunning as exc:
        log.warning("%s; skipping this run", exc)
        return 0
    except KeyboardInterrupt:
        log.warning("interrupted; last good images kept")
        return 130
    except Exception as exc:
        log.error("run failed: %s", exc)
        log.debug("traceback", exc_info=True)
        log.error("last good images kept in %s", cfg.output_dir)
        return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit status."""
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    log.info("snowgrid %s, config %s", __version__, cfg.path)
    if args.once or args.date:
        return _attempt(cfg, args.force, args.date)

    log.info("loop mode: running every %d h (Ctrl+C to stop)", cfg.interval_hours)
    force = args.force
    while True:
        status = _attempt(cfg, force, None)
        if status == 130:
            return status
        force = False
        try:
            time.sleep(cfg.interval_hours * 3600)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
