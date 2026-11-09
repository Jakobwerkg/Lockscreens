#!/usr/bin/env python3
"""
data_updater.py
Tiered data fetcher for the Hydro screen.

- CORE stations     → current value + last 5 days (when history endpoint is ready)
- SECONDARY stations → current value + last 3 hours (or just current for now)
- All other selected stations from selected_catchment_stations.json

Small footprint. Designed to run in a background thread from hydro.py.
"""

import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ehyd_data import get_current_values, get_recent_observations

# ── config ───────────────────────────────────────────────────────────────────
SELECTED_FILE = Path("selected_catchment_stations.json")
CACHE_FILE = Path("hydro_data_cache.json")

# You will fill these later (we can select together)
CORE_HZBNR: List[str] = [
    # === Upper Inn ===
    "201194",   # Prutz
    "201293",   # Landeck-Perjen
    "201319",   # Imst
    "201392",   # Huben (Ötztal)
    "201335",   # St. Leonhard im Pitztal

    # === Middle Inn (core area) ===
    "201459",   # Magerbach
    "201475",   # Zirl
    "201525",   # Innsbruck (highest priority)
    "201624",   # Innsbruck-Reichenau
    "201673",   # Schwaz
    "201681",   # Jenbach-Rotholz

    # === Lower Inn ===
    "201806",   # Brixlegg
    "201814",   # Rattenberg
    "201889",   # Kirchbichl-Bichlwang
    "201905",   # Kufstein

    # === Important tributaries / side areas ===
    "201178",   # Kajetansbrücke
    "201756",   # Zell am Ziller
    "202572",   # Kirchberg (Brixental)

    # === Donau (selected key stations) ===
    "207019",
    "207100",
    "207175",

    # === Drau (selected key stations) ===
    "113118",   # Oberdrauburg
    "113761",   # Wernberg
    "113779",   # Rosenbach
]

SECONDARY_HZBNR: List[str] = [
    # Add more later
]

# Precipitation stations close to the CORE river gauges
# (selected via proximity analysis — ~50 stations)
CORE_PRECIP_HZBNR: List[str] = [
    "113118",  # 0.0 km from 113118 (Oberdrauburg)
    "113761",  # 0.0 km from 113761 (Wernberg)
    "113779",  # 0.0 km from 113779 (Rosenbach)
    "102483",  # 0.3 km from 201673 (Schwaz)
    "103119",  # 0.5 km from 201814 (Radfeld)
    "106963",  # 0.6 km from 207100 (Grein)
    "102061",  # 0.7 km from 201335 (St.Leonhard i.P.)
    "102509",  # 0.8 km from 201681 (Rotholz)
    "120022",  # 1.9 km from 202572 (Hall in Tirol)
    "101790",  # 2.2 km from 201194 (Ried im Oberinntal)
    "103036",  # 2.2 km from 201475 (Inzing)
    "101816",  # 2.4 km from 201194 (Ladis-Neuegg)
    "102517",  # 3.2 km from 201681 (Schlitterberg)
    "102004",  # 3.5 km from 201319 (Imst-Oberstadt)
    "102236",  # 3.6 km from 201392 (Längenfeld)
    "119586",  # 3.8 km from 201905 (Brentenjoch)
    "107870",  # 4.0 km from 207175 (Stockerau)
    "102475",  # 4.4 km from 201673 (Weerberg)
    "114512",  # 4.4 km from 113118 (Irschen-Leppen)
    "119404",  # 4.5 km from 201624 (Innsbruck-Seegrube)
    "102269",  # 4.6 km from 201459 (Ochsengarten-Obergut)
    "102434",  # 5.0 km from 202572 (Kleinvolderberg)
    "119388",  # 5.0 km from 201392 (Gries)
    "106930",  # 5.1 km from 207100 (Saxen-Au)
    "103309",  # 5.2 km from 201475 (Axams)
    "115634",  # 5.2 km from 207175 (Kierling)
    "113563",  # 5.3 km from 113761 (Ossiach)
    "102749",  # 5.4 km from 201814 (Brandenberg)
    "116087",  # 5.4 km from 207100 (Neustadtl)
    "114629",  # 5.4 km from 113761 (Velden-Weinzierl)
    "102285",  # 5.8 km from 201459 (Obsteig)
    "101717",  # 5.8 km from 201178 (Spiss)
    "102954",  # 6.0 km from 201459 (Nassereith)
    "119560",  # 6.2 km from 201335 (Hintere Fundusalm)
    "119453",  # 6.4 km from 202572 (Halltal-Oberbergstollen)
    "119438",  # 6.4 km from 201673 (Stallenhütte)
    "115238",  # 6.5 km from 201319 (Imst-Obermarkter Alm)
    "101659",  # 6.6 km from 113761 (Faak am See)
    "102251",  # 6.6 km from 201459 (Oetz)
    "104505",  # 6.7 km from 207019 (Schardenberg)
    "117002",  # 6.7 km from 201673 (Loassattel)
    "114942",  # 6.8 km from 113118 (Nikolsdorf)
    "102228",  # 7.3 km from 201392 (Sölden)
    "120030",  # 7.5 km from 201475 (Inzinger Alm-Kaserboden)
    "102079",  # 7.5 km from 201335 (Jerzens-Ritzenried)
    "101873",  # 7.5 km from 201335 (Kaunertal-Vergötschen)
    "103192",  # 7.6 km from 201756 (Gschößwand)
    "104455",  # 7.8 km from 207019 (Wernstein)
    "115089",  # 7.9 km from 207175 (Unterkirchbach)
    "103184",  # 8.0 km from 201756 (Brandberger Kolmhaus)
]

UPDATE_INTERVAL_SEC = 300          # 5 minutes for current values
CORE_HISTORY_INTERVAL_SEC = 900    # 15 minutes for 5-day history (when implemented)


# ── helpers ──────────────────────────────────────────────────────────────────
def load_selected_stations() -> Dict[str, List[str]]:
    if not SELECTED_FILE.exists():
        raise FileNotFoundError(f"{SELECTED_FILE} not found. Run filter_stations.py first.")
    with open(SELECTED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "rivers": data.get("rivers", {}),
        "niederschlag": data.get("niederschlag_same_gewaesser", []),
        "all": data.get("all_selected_hzbnr", []),
    }


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"current": {}, "history": {}, "last_update": 0}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ── main class / functions ───────────────────────────────────────────────────
class DataUpdater:
    def __init__(self):
        self.selected = load_selected_stations()
        self.cache = _load_cache()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def get_all_current(self) -> dict:
        """Return latest current values for all selected stations."""
        with self._lock:
            return self.cache.get("current", {}).copy()

    def get_history(self, hzbnr: str) -> list:
        """Return last 5 days (or whatever is cached). Currently stub."""
        with self._lock:
            return self.cache.get("history", {}).get(hzbnr, [])

    def update_current(self):
        """Fetch current values for all selected stations."""
        all_hz = self.selected["all"]
        if not all_hz:
            return

        print(f"[data_updater] Fetching current values for {len(all_hz)} stations...")
        current = get_current_values(all_hz)

        with self._lock:
            self.cache["current"] = current
            self.cache["last_update"] = time.time()
        _save_cache(self.cache)
        print(f"[data_updater] Current values updated ({len(current)} stations)")

    def update_core_history(self):
        """Fetch recent history (last 5 days) for CORE + CORE_PRECIP stations."""
        core_stations = CORE_HZBNR + CORE_PRECIP_HZBNR
        if not core_stations:
            return

        print(f"[data_updater] Updating history for {len(core_stations)} core stations...")
        for hz in core_stations:
            try:
                history = get_recent_observations(hz, hours=120)
                with self._lock:
                    if "history" not in self.cache:
                        self.cache["history"] = {}
                    self.cache["history"][hz] = history
            except Exception as e:
                print(f"[data_updater] History error for {hz}: {e}")

        _save_cache(self.cache)
        print("[data_updater] Core history updated")

    def _background_loop(self):
        last_current = 0
        last_history = 0

        while self._running:
            now = time.time()

            # Current values (all stations)
            if now - last_current > UPDATE_INTERVAL_SEC:
                try:
                    self.update_current()
                except Exception as e:
                    print(f"[data_updater] Error updating current: {e}")
                last_current = now

            # Core history (less frequent)
            if now - last_history > CORE_HISTORY_INTERVAL_SEC:
                try:
                    self.update_core_history()
                except Exception as e:
                    print(f"[data_updater] Error updating history: {e}")
                last_history = now

            time.sleep(30)   # check every 30s

    def start(self):
        """Start background update thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._background_loop, daemon=True)
        self._thread.start()
        print("[data_updater] Background updater started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[data_updater] Stopped")


# ── quick test / standalone use ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=== DataUpdater test ===")
    updater = DataUpdater()

    print(f"Total selected stations: {len(updater.selected['all'])}")
    print(f"Core stations: {CORE_HZBNR}")

    # One-shot update
    updater.update_current()
    current = updater.get_all_current()
    print(f"Current values received: {len(current)}")

    # Example: show one Inn station
    if "201525" in current:
        d = current["201525"]
        print(f"\nExample - Innsbruck (201525): {d.get('wert')} {d.get('einheit')} @ {d.get('zeitpunkt')}")

    print("\nStarting background thread for 60 seconds (Ctrl+C to stop)...")
    updater.start()
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    updater.stop()
    print("Test finished.")
