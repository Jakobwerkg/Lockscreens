#!/usr/bin/env python3
"""
filter_stations.py
Uses the stations already fetched in ehyd_cache.json (or re-fetches if missing)
and creates focused lists for the Hydro screen:

- Main river gauges: gewaesser in ["Inn", "Donau", "Drau"]
- Niederschlag (nlv) in the catchment areas (Tirol-focused for now)

Outputs ready-to-use lists you can copy into hydro.py
"""

import json
from pathlib import Path
from ehyd_data import get_all_stations

CACHE_FILE = Path("ehyd_cache.json")
OUTPUT_FILE = Path("selected_catchment_stations.json")

def load_or_fetch_stations():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if "stations" in cache and len(cache["stations"]) > 100:
                print(f"Loaded {len(cache['stations'])} stations from cache.")
                return cache["stations"]
        except Exception:
            pass
    print("Cache missing or too small → fetching fresh station list (may take 30-60s)...")
    return get_all_stations()

def main():
    stations = load_or_fetch_stations()

    # 1. Main river stations (exact gewaesser match)
    target_rivers = ["Inn", "Donau", "Drau"]
    river_stations = {
        hzbnr: data for hzbnr, data in stations.items()
        if data.get("gewaesser") in target_rivers
    }

    print("\n=== Main river gauges ===")
    for river in target_rivers:
        count = sum(1 for d in river_stations.values() if d.get("gewaesser") == river)
        print(f"  {river}: {count} stations")

    # 2. Niederschlag stations in the same catchment (exact same gewaesser)
    nlv_in_catchment = {
        hzbnr: data for hzbnr, data in stations.items()
        if data.get("type") == "nlv" and data.get("gewaesser") in target_rivers
    }

    print(f"\n=== Niederschlag (nlv) stations with same gewaesser ===")
    for river in target_rivers:
        count = sum(1 for d in nlv_in_catchment.values() if d.get("gewaesser") == river)
        print(f"  {river}: {count} precipitation stations")
    print(f"  Total: {len(nlv_in_catchment)}")

    # Combine into one clean structure for hydro.py
    selected = {
        "rivers": {
            "Inn":   [hz for hz, d in river_stations.items() if d["gewaesser"] == "Inn"],
            "Donau": [hz for hz, d in river_stations.items() if d["gewaesser"] == "Donau"],
            "Drau":  [hz for hz, d in river_stations.items() if d["gewaesser"] == "Drau"],
        },
        "niederschlag_same_gewaesser": list(nlv_in_catchment.keys()),
        "all_selected_hzbnr": list(river_stations.keys()) + list(nlv_in_catchment.keys()),
        "metadata": {
            "generated_from": "ehyd_cache.json + filter_stations.py",
            "note": "Inn/Donau/Drau = exact gewaesser match for both river gauges and nlv precipitation stations"
        }
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2, ensure_ascii=False)

    print(f"\nSaved → {OUTPUT_FILE.resolve()}")
    print(f"Total unique HZBNR selected: {len(set(selected['all_selected_hzbnr']))}")
    print("Ready to use in hydro.py")
    print("\nYou can now copy the lists from the JSON into hydro.py HYDRO_IMAGES or a config.")

if __name__ == "__main__":
    main()
