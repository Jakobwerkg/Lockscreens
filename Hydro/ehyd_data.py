#!/usr/bin/env python3
"""
ehyd_data.py – lightweight client for eHYD OGC API
Focus: current measurements (pegel_aktuell, niederschlag_aktuell, grundwasser_aktuell)
+ full station inventory (HZBNR + metadata)

Small footprint: only requests + stdlib. Cache last results to JSON.
Designed to be called periodically from hydro.py background thread.

Usage example:
    from ehyd_data import get_all_stations, get_current_values
    stations = get_all_stations()
    current = get_current_values(hzbnr_list=["201525", "202713"])   # only these
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import requests

# ── config ───────────────────────────────────────────────────────────────────
CACHE_FILE = "ehyd_cache.json"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HydroScreen/1.0 (Raspberry Pi)"})

# OGC API base
OGC_BASE = "https://gis.lfrz.gv.at/api/geodata/i000501/ogc/features/v1/collections"

# Collections we care about
MESSSTELLEN_COLLECTIONS = [
    "i000501:messstellen_owf",   # Oberflächenwasser / pegel (Q, W)
    "i000501:messstellen_gw",    # Grundwasser
    "i000501:messstellen_nlv",   # Niederschlag
    "i000501:messstellen_qu",    # Quellen
]

AKTUELL_COLLECTIONS = [
    "i000501:pegel_aktuell",           # current Q / W
    "i000501:niederschlag_aktuell",    # current precipitation
    "i000501:grundwasser_aktuell",     # current groundwater
]


# ── helpers ──────────────────────────────────────────────────────────────────
def _get_json(url: str, params: Optional[dict] = None) -> dict:
    """GET with timeout + basic retry."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ── station inventory ────────────────────────────────────────────────────────
def get_messstellen(collection: str, limit: int = 10000) -> List[dict]:
    """Fetch raw features from one messstellen_* collection."""
    url = f"{OGC_BASE}/{collection}/items"
    params = {"limit": limit, "f": "json"}
    data = _get_json(url, params)
    return data.get("features", [])


def get_all_stations() -> Dict[str, dict]:
    """
    Return {hzbnr: {"name": str, "gewaesser": str, "hydrodienst": str,
                    "lat": float, "lon": float, "type": str}}
    type = owf | gw | nlv | qu
    """
    cache = _load_cache()
    if "stations" in cache and (datetime.now().timestamp() - cache.get("stations_ts", 0) < 86400):
        return cache["stations"]

    stations: Dict[str, dict] = {}
    type_map = {
        "i000501:messstellen_owf": "owf",
        "i000501:messstellen_gw": "gw",
        "i000501:messstellen_nlv": "nlv",
        "i000501:messstellen_qu": "qu",
    }

    for coll in MESSSTELLEN_COLLECTIONS:
        try:
            feats = get_messstellen(coll)
            t = type_map.get(coll, "unknown")
            for feat in feats:
                props = feat.get("properties", {})
                hzbnr = str(props.get("hzbnr") or props.get("HZBNR") or "")
                if not hzbnr:
                    continue
                geom = feat.get("geometry", {}).get("coordinates", [None, None])
                stations[hzbnr] = {
                    "name": props.get("messstelle") or props.get("name", ""),
                    "gewaesser": props.get("gewaesser", ""),
                    "hydrodienst": props.get("hydrodienst", ""),
                    "lat": geom[1] if geom else None,
                    "lon": geom[0] if geom else None,
                    "type": t,
                }
        except Exception as e:
            print(f"[ehyd_data] Warning: failed to load {coll}: {e}")

    cache["stations"] = stations
    cache["stations_ts"] = datetime.now().timestamp()
    _save_cache(cache)
    return stations


# ── current measurements ─────────────────────────────────────────────────────
def get_aktuell(collection: str, hzbnr_filter: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    Fetch current values from one *_aktuell collection.
    Returns {hzbnr: {"parameter": "Q", "wert": float, "einheit": "m³/s",
                     "zeitpunkt": str, "name": str, "gewaesser": str}}
    """
    url = f"{OGC_BASE}/{collection}/items"
    params = {"limit": 10000, "f": "json"}
    data = _get_json(url, params)
    result = {}

    for feat in data.get("features", []):
        props = feat.get("properties", {})
        hzbnr = str(props.get("hzbnr", ""))
        if not hzbnr:
            continue
        if hzbnr_filter and hzbnr not in hzbnr_filter:
            continue

        result[hzbnr] = {
            "parameter": props.get("parameter", ""),
            "wert": props.get("wert"),
            "einheit": props.get("einheit", ""),
            "zeitpunkt": props.get("zeitpunkt", ""),
            "name": props.get("messstelle", ""),
            "gewaesser": props.get("gewaesser", ""),
            "hydrodienst": props.get("hydrodienst", ""),
        }
    return result


def get_current_values(hzbnr_list: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    Merge current values from all aktuell collections.
    If hzbnr_list is given, only fetch those stations (much faster).
    Result: {hzbnr: {..current data.. , "source_collection": str}}
    """
    cache = _load_cache()
    cache_key = f"current_{hash(tuple(sorted(hzbnr_list or [])))}"

    # simple 5-min cache
    if cache_key in cache:
        ts = cache.get(f"{cache_key}_ts", 0)
        if time.time() - ts < 300:
            return cache[cache_key]

    merged: Dict[str, dict] = {}

    for coll in AKTUELL_COLLECTIONS:
        try:
            current = get_aktuell(coll, hzbnr_filter=hzbnr_list)
            for hzbnr, data in current.items():
                data["source_collection"] = coll
                merged[hzbnr] = data
        except Exception as e:
            print(f"[ehyd_data] Warning fetching {coll}: {e}")

    cache[cache_key] = merged
    cache[f"{cache_key}_ts"] = time.time()
    _save_cache(cache)
    return merged


# ── convenience for last 5 days (stub – extend later) ────────────────────────
def get_recent_observations(hzbnr: str, hours: int = 120) -> List[dict]:
    """
    Try to fetch recent observations for a station using time filter on OGC API.
    Returns list of dicts with timestamp and value.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    datetime_filter = f"{start_time.isoformat()}/{end_time.isoformat()}"

    # Try on pegel_aktuell first (most relevant for Q/W)
    collection = "i000501:pegel_aktuell"
    url = f"{OGC_BASE}/{collection}/items"

    params = {
        "limit": 2000,
        "f": "json",
        "datetime": datetime_filter,
    }

    try:
        data = _get_json(url, params)
        observations = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            if str(props.get("hzbnr", "")) != str(hzbnr):
                continue
            obs = {
                "timestamp": props.get("zeitpunkt"),
                "wert": props.get("wert"),
                "einheit": props.get("einheit"),
                "parameter": props.get("parameter"),
            }
            if obs["timestamp"] and obs["wert"] is not None:
                observations.append(obs)

        if observations:
            return sorted(observations, key=lambda x: x["timestamp"])
    except Exception as e:
        print(f"[ehyd_data] Could not fetch history for {hzbnr}: {e}")

    return []


if __name__ == "__main__":
    print("Testing ehyd_data.py ...")
    print("Fetching small set of current values (hzbnr 201525, 202713, 101303)...")
    data = get_current_values(["201525", "202713", "101303"])
    for hz, d in data.items():
        print(f"  {hz} | {d.get('parameter')} = {d.get('wert')} {d.get('einheit')} @ {d.get('zeitpunkt')[:16]}")

    print("\nTotal stations in inventory:", len(get_all_stations()))
    print("Cache file:", os.path.abspath(CACHE_FILE))
