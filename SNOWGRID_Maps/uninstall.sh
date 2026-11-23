#!/usr/bin/env bash
# Remove the SNOWGRID snow-depth maps: systemd units, venv, Natural Earth data,
# cache and images. The source code in this directory is left in place.
#
#   ./uninstall.sh              # remove everything
#   ./uninstall.sh --keep-data  # keep output images and the NetCDF cache
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$APP_DIR/config.toml"
VENV="$APP_DIR/.venv"
SYSTEM_UNIT_DIR="/etc/systemd/system"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

KEEP_DATA=0
case "${1:-}" in
    --keep-data) KEEP_DATA=1 ;;
    "") ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
esac

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
[[ $EUID -ne 0 ]] || { echo "run as your normal user, not root" >&2; exit 1; }

# Paths from config.toml, falling back to the defaults if it is unreadable.
OUTPUT_DIR="$APP_DIR/output"; CACHE_DIR="$APP_DIR/cache"; NE_DIR="$APP_DIR/naturalearth"
if CFG_VARS="$(cd "$APP_DIR" && python3 -I -c '
import shlex, sys
sys.path.insert(0, ".")
from snowgrid.config import load_config
c = load_config(sys.argv[1])
for k, v in {"OUTPUT_DIR": c.output_dir, "CACHE_DIR": c.cache_dir, "NE_DIR": c.natural_earth_dir}.items():
    print(f"{k}={shlex.quote(str(v))}")
' "$CONFIG" 2>/dev/null)"; then
    eval "$CFG_VARS"
fi

# Remove a directory only if it is a real, non-critical path.
safe_rm_dir() {
    local d="$1" real
    [[ -n "$d" && -e "$d" ]] || return 0
    real="$(cd "$d" && pwd -P)"
    case "$real" in
        /|/home|/root|/usr|/etc|/var|/opt|/tmp|"$HOME"|"$APP_DIR"|"$(dirname "$APP_DIR")")
            echo "  refusing to delete $real" >&2; return 0 ;;
    esac
    echo "  removing $real"
    rm -rf -- "$real"
}

say "Stopping and removing system units"
sudo systemctl disable --now snowgrid.timer 2>/dev/null || true
sudo systemctl stop snowgrid.service 2>/dev/null || true
sudo rm -f -- "$SYSTEM_UNIT_DIR/snowgrid.timer" "$SYSTEM_UNIT_DIR/snowgrid.service"
sudo systemctl daemon-reload
sudo systemctl reset-failed snowgrid.service snowgrid.timer 2>/dev/null || true

say "Removing display user unit"
if systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user disable --now snowgrid-display.service 2>/dev/null || true
    rm -f -- "$USER_UNIT_DIR/snowgrid-display.service"
    systemctl --user daemon-reload
    systemctl --user reset-failed snowgrid-display.service 2>/dev/null || true
else
    rm -f -- "$USER_UNIT_DIR/snowgrid-display.service"
    echo "  (no user session bus: unit file removed; it is gone after the next login)"
fi

say "Removing venv and Natural Earth data"
safe_rm_dir "$VENV"
safe_rm_dir "$NE_DIR"

if [[ $KEEP_DATA == 1 ]]; then
    say "Keeping images ($OUTPUT_DIR) and cache ($CACHE_DIR)"
else
    say "Removing images and cache"
    safe_rm_dir "$OUTPUT_DIR"
    safe_rm_dir "$CACHE_DIR"
fi
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf -- {} + 2>/dev/null || true

say "Done. apt packages (feh, python3-venv, ...) were left installed."
echo "  Source code remains in $APP_DIR"
