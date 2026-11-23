#!/usr/bin/env bash
# Install the SNOWGRID snow-depth maps on a Raspberry Pi (Raspberry Pi OS, X11).
#
#   cd ~/Lockscreens/SNOWGRID_Maps && ./install.sh
#
# Run as the normal desktop user (not root); sudo is used where needed.
# Safe to re-run: after editing config.toml ([schedule], [display], paths),
# run it again to update the venv, Natural Earth data and systemd units.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$APP_DIR/config.toml"
VENV="$APP_DIR/.venv"
UNIT_SRC="$APP_DIR/systemd"
SYSTEM_UNIT_DIR="/etc/systemd/system"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "run as your normal user, not root (sudo is used where needed)"
command -v sudo >/dev/null || die "sudo is required"
command -v systemctl >/dev/null || die "systemd is required"
[[ -f "$CONFIG" ]] || die "config not found: $CONFIG"

# ── Python version ───────────────────────────────────────────────────────────
command -v python3 >/dev/null || { sudo apt-get update && sudo apt-get install -y python3; }
python3 - <<'PY' || die "Python >= 3.11 is required (Raspberry Pi OS Bookworm or newer)"
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY

# ── read config.toml (stdlib only, same code the app uses) ───────────────────
say "Reading $CONFIG"
CFG_VARS="$(cd "$APP_DIR" && python3 -I -c '
import shlex, sys
sys.path.insert(0, ".")
from snowgrid.config import load_config
c = load_config(sys.argv[1])
for k, v in {
    "OUTPUT_DIR": c.output_dir, "CACHE_DIR": c.cache_dir, "NE_DIR": c.natural_earth_dir,
    "INTERVAL_HOURS": c.interval_hours, "DISPLAY_ENABLED": int(c.display.enabled),
    "RELOAD_S": c.display.reload_s, "SLIDESHOW_DELAY_S": c.display.slideshow_delay_s,
}.items():
    print(f"{k}={shlex.quote(str(v))}")
' "$CONFIG")" || die "config.toml is invalid (see message above)"
eval "$CFG_VARS"
echo "  output dir:   $OUTPUT_DIR"
echo "  cache dir:    $CACHE_DIR"
echo "  NaturalEarth: $NE_DIR"
echo "  interval:     every ${INTERVAL_HOURS} h"
echo "  display:      $([[ $DISPLAY_ENABLED == 1 ]] && echo enabled || echo disabled)"

# ── apt packages ─────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
APT_PKGS=(python3-venv python3-pip ca-certificates)
[[ $DISPLAY_ENABLED == 1 ]] && APT_PKGS+=(feh)
if [[ $ARCH != aarch64 ]]; then
    # No reliable pip wheels for cartopy & friends here: use Debian's builds.
    APT_PKGS+=(python3-cartopy python3-numpy python3-matplotlib python3-xarray
               python3-netcdf4 python3-requests)
fi
say "Installing apt packages ($ARCH): ${APT_PKGS[*]}"
sudo apt-get update
sudo apt-get install -y --no-install-recommends "${APT_PKGS[@]}"

# ── virtualenv ───────────────────────────────────────────────────────────────
if [[ $ARCH == aarch64 ]]; then
    VENV_ARGS=()
    WANT_SYSTEM_SITE=false
else
    VENV_ARGS=(--system-site-packages)
    WANT_SYSTEM_SITE=true
fi
if [[ -x "$VENV/bin/python" ]] && ! grep -q "include-system-site-packages = $WANT_SYSTEM_SITE" "$VENV/pyvenv.cfg"; then
    say "Recreating venv (system-site-packages setting changed)"
    rm -rf -- "$VENV"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
    say "Creating venv in $VENV ${VENV_ARGS[*]:-}"
    python3 -m venv "${VENV_ARGS[@]}" "$VENV"
fi
say "Installing Python dependencies"
"$VENV/bin/python" -m pip install --upgrade pip
if [[ $ARCH == aarch64 ]]; then
    "$VENV/bin/python" -m pip install --upgrade --prefer-binary -r "$APP_DIR/requirements.txt"
else
    # Keep Debian's numpy/cartopy (ABI-matched); only add what is missing.
    "$VENV/bin/python" -m pip install --upgrade-strategy only-if-needed -r "$APP_DIR/requirements.txt"
fi
"$VENV/bin/python" -c 'import cartopy, matplotlib, netCDF4, numpy, requests, xarray; print("  cartopy", cartopy.__version__, "| matplotlib", matplotlib.__version__, "| numpy", numpy.__version__)'

# ── Natural Earth (offline overlays) ─────────────────────────────────────────
say "Downloading Natural Earth data to $NE_DIR"
(cd "$APP_DIR" && "$VENV/bin/python" -m snowgrid.naturalearth --config "$CONFIG") \
    || die "Natural Earth download failed (network?) - re-run ./install.sh"

mkdir -p "$OUTPUT_DIR" "$CACHE_DIR"

# ── systemd units ────────────────────────────────────────────────────────────
# render_unit TEMPLATE DEST: replace @PLACEHOLDERS@ (no sed escaping pitfalls).
render_unit() {
    APP_DIR="$APP_DIR" VENV="$VENV" USER_NAME="$(id -un)" GROUP_NAME="$(id -gn)" \
    OUTPUT_DIR="$OUTPUT_DIR" CACHE_DIR="$CACHE_DIR" INTERVAL_HOURS="$INTERVAL_HOURS" \
    RELOAD_S="$RELOAD_S" SLIDESHOW_DELAY_S="$SLIDESHOW_DELAY_S" \
    python3 -I -c '
import os, sys
text = open(sys.argv[1]).read()
for key, env in [("APP_DIR", "APP_DIR"), ("VENV", "VENV"), ("USER", "USER_NAME"),
                 ("GROUP", "GROUP_NAME"), ("OUTPUT_DIR", "OUTPUT_DIR"), ("CACHE_DIR", "CACHE_DIR"),
                 ("INTERVAL_HOURS", "INTERVAL_HOURS"), ("RELOAD_S", "RELOAD_S"),
                 ("SLIDESHOW_DELAY_S", "SLIDESHOW_DELAY_S")]:
    text = text.replace(f"@{key}@", os.environ[env])
if "@" in "".join(l for l in text.splitlines() if not l.lstrip().startswith("#")):
    sys.exit(f"unreplaced placeholder in {sys.argv[1]}")
open(sys.argv[2], "w").write(text)
' "$1" "$2"
}

TMP_UNITS="$(mktemp -d)"
trap 'rm -rf -- "$TMP_UNITS"' EXIT

say "Installing system units: snowgrid.service, snowgrid.timer"
render_unit "$UNIT_SRC/snowgrid.service" "$TMP_UNITS/snowgrid.service"
render_unit "$UNIT_SRC/snowgrid.timer" "$TMP_UNITS/snowgrid.timer"
sudo install -m 0644 "$TMP_UNITS/snowgrid.service" "$SYSTEM_UNIT_DIR/snowgrid.service"
sudo install -m 0644 "$TMP_UNITS/snowgrid.timer" "$SYSTEM_UNIT_DIR/snowgrid.timer"
sudo systemctl daemon-reload
if command -v systemd-analyze >/dev/null; then
    sudo systemd-analyze verify "$SYSTEM_UNIT_DIR/snowgrid.service" "$SYSTEM_UNIT_DIR/snowgrid.timer" \
        || warn "systemd-analyze reported issues (see above)"
fi

# ── test run ─────────────────────────────────────────────────────────────────
say "Test run (systemctl start snowgrid.service) - downloads the latest day and renders both maps"
TEST_OK=1
if ! sudo systemctl start snowgrid.service; then
    TEST_OK=0
fi
sudo journalctl -u snowgrid.service -n 15 --no-pager -o cat || true
if [[ $TEST_OK == 1 && -s "$OUTPUT_DIR/snow_depth.png" && -s "$OUTPUT_DIR/snow_change_24h.png" ]]; then
    echo "  OK: $OUTPUT_DIR/snow_depth.png, $OUTPUT_DIR/snow_change_24h.png"
else
    TEST_OK=0
    warn "test run failed - the timer is still installed and will retry; see 'journalctl -u snowgrid'"
fi

say "Enabling snowgrid.timer (at boot + every ${INTERVAL_HOURS} h)"
sudo systemctl enable --now snowgrid.timer

# ── optional display (user unit) ─────────────────────────────────────────────
if systemctl --user show-environment >/dev/null 2>&1; then
    HAVE_USER_BUS=1
else
    HAVE_USER_BUS=0
fi
if [[ $DISPLAY_ENABLED == 1 ]]; then
    say "Installing user unit snowgrid-display.service (feh slideshow)"
    mkdir -p "$USER_UNIT_DIR"
    render_unit "$UNIT_SRC/snowgrid-display.service" "$USER_UNIT_DIR/snowgrid-display.service"
    if [[ $HAVE_USER_BUS == 1 ]]; then
        systemctl --user daemon-reload
        systemctl --user enable snowgrid-display.service
        systemctl --user restart snowgrid-display.service || warn "display did not start yet (no X session?) - it will start with the desktop"
    else
        warn "no systemd user session here; after logging in to the desktop run:"
        echo "    systemctl --user daemon-reload && systemctl --user enable --now snowgrid-display.service"
    fi
else
    if [[ -f "$USER_UNIT_DIR/snowgrid-display.service" ]]; then
        say "Display disabled in config: removing snowgrid-display.service"
        if [[ $HAVE_USER_BUS == 1 ]]; then
            systemctl --user disable --now snowgrid-display.service 2>/dev/null || true
        fi
        rm -f -- "$USER_UNIT_DIR/snowgrid-display.service"
        [[ $HAVE_USER_BUS == 1 ]] && systemctl --user daemon-reload
    fi
fi

say "Done"
cat <<EOF
  Images:   $OUTPUT_DIR/snow_depth.png
            $OUTPUT_DIR/snow_change_24h.png  (dated copies in $OUTPUT_DIR/archive/)
  Timer:    systemctl list-timers snowgrid.timer
  Logs:     journalctl -u snowgrid -e
  Run now:  sudo systemctl start snowgrid.service
EOF
[[ $DISPLAY_ENABLED == 1 ]] && echo "  Display:  systemctl --user status snowgrid-display.service"
[[ $TEST_OK == 1 ]] || exit 1
exit 0
