"""Show both maps with feh on one chosen monitor.

``[display] screen`` uses the same numbering as the other Lockscreens apps:
monitors reported as connected by ``xrandr``, sorted left to right (then top
to bottom), so 0 is the leftmost monitor.

The feh window is placed exactly over that monitor (``--geometry WxH+X+Y``,
borderless) instead of relying on ``--fullscreen``, which lets the window
manager pick the monitor. If xrandr fails or the monitor does not exist, it
falls back to plain fullscreen.

Run by ``snowgrid-display.service``; ``python -m snowgrid.display --dry-run``
prints the feh command instead of starting it.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from snowgrid.config import Config, ConfigError, load_config

log = logging.getLogger("snowgrid.display")

Monitor = tuple[int, int, int, int]  # x, y, width, height
_XRANDR_RE = re.compile(r"\bconnected\b.*?(\d+)x(\d+)\+(\d+)\+(\d+)")


def parse_xrandr(text: str) -> list[Monitor]:
    """Connected, active monitors from ``xrandr`` output, left to right."""
    mons = [
        (int(m.group(3)), int(m.group(4)), int(m.group(1)), int(m.group(2)))
        for m in _XRANDR_RE.finditer(text)
    ]
    return sorted(mons)


def list_monitors() -> list[Monitor]:
    """Query ``xrandr`` on ``$DISPLAY``; empty list if that is not possible."""
    try:
        out = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("xrandr failed (%s)", exc)
        return []
    return parse_xrandr(out)


def feh_command(cfg: Config, monitors: list[Monitor]) -> list[str]:
    """Build the feh command line for the configured screen."""
    d = cfg.display
    cmd = [
        "feh", "--hide-pointer", "--auto-zoom", "--no-menus", "--quiet", "--image-bg", "black",
        "--reload", str(d.reload_s), "--slideshow-delay", str(d.slideshow_delay_s),
    ]
    if d.screen < len(monitors):
        x, y, w, h = monitors[d.screen]
        log.info("screen %d of %d: %dx%d at +%d+%d", d.screen, len(monitors), w, h, x, y)
        cmd += ["--borderless", "--geometry", f"{w}x{h}+{x}+{y}"]
    else:
        log.warning("screen %d not found (%d monitor(s) detected); using plain fullscreen",
                    d.screen, len(monitors))
        cmd += ["--fullscreen"]
    cmd += [str(cfg.output_dir / "snow_depth.png"), str(cfg.output_dir / "snow_change_24h.png")]
    return cmd


def main(argv: list[str] | None = None) -> int:
    """Start feh (replacing this process, so systemd supervises feh directly)."""
    ap = argparse.ArgumentParser(description="Show the SNOWGRID maps with feh on one monitor.")
    ap.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config.toml")
    ap.add_argument("--dry-run", action="store_true", help="print the feh command and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    cmd = feh_command(cfg, list_monitors())
    if args.dry_run:
        print(" ".join(cmd))
        return 0
    feh = shutil.which("feh")
    if feh is None:
        log.error("feh is not installed (sudo apt install feh)")
        return 1
    sys.stdout.flush()
    os.execv(feh, cmd)
    return 1  # not reached


if __name__ == "__main__":
    sys.exit(main())
