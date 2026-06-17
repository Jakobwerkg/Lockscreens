import io
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image

BASE_URL   = "https://cdn.fmi.fi/demos/eumetnet-web-site-radar-animator/new-images/"
CACHE_DIR  = Path(__file__).parent / "cache"
OUTPUT_GIF = Path(__file__).parent / "opera_radar.gif"


def round_down_5min(dt):
    return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)


def _frame_url(dt):
    return BASE_URL + dt.strftime("%Y%m%d%H%M") + "_Odyssey_NewMax_composite.gif"


def _load_cached(cache_path):
    try:
        img = Image.open(cache_path).convert("RGBA")
        return img.copy()
    except Exception:
        cache_path.unlink(missing_ok=True)
        return None


def download_single_frame(dt):
    """Download one frame. Returns (datetime, Image) or None if unavailable."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{dt.strftime('%Y%m%d%H%M')}.gif"
    if cache_path.exists():
        img = _load_cached(cache_path)
        if img:
            return (dt, img)
    try:
        resp = requests.get(_frame_url(dt), timeout=10)
        if resp.status_code == 200:
            cache_path.write_bytes(resp.content)
            return (dt, Image.open(io.BytesIO(resp.content)).convert("RGBA").copy())
    except Exception:
        pass
    return None


def download_frames(n_hours=2.0, progress_cb=None):
    """Return list of (datetime, Image) for the last n_hours, missing frames skipped."""
    CACHE_DIR.mkdir(exist_ok=True)
    now   = round_down_5min(datetime.now(timezone.utc))
    total = int(n_hours * 12) + 1
    frames = []
    for idx, i in enumerate(range(total - 1, -1, -1)):
        dt         = now - timedelta(minutes=5 * i)
        cache_path = CACHE_DIR / f"{dt.strftime('%Y%m%d%H%M')}.gif"
        if cache_path.exists():
            img = _load_cached(cache_path)
            if img:
                frames.append((dt, img))
                if progress_cb:
                    progress_cb(idx + 1, total)
                continue
        try:
            resp = requests.get(_frame_url(dt), timeout=10)
            if resp.status_code == 200:
                cache_path.write_bytes(resp.content)
                img = Image.open(io.BytesIO(resp.content)).convert("RGBA").copy()
                frames.append((dt, img))
        except Exception:
            pass
        if progress_cb:
            progress_cb(idx + 1, total)
    return frames


def save_animation(frames, output_path=OUTPUT_GIF, frame_ms=200):
    if not frames:
        raise ValueError("No frames to save.")
    imgs = [img.convert("P", palette=Image.ADAPTIVE) for _, img in frames]
    imgs[0].save(output_path, save_all=True, append_images=imgs[1:],
                 loop=0, duration=frame_ms, optimize=False)
    return output_path


def purge_old_cache(keep_hours=6.0):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=keep_hours)
    for f in CACHE_DIR.glob("*.gif"):
        try:
            ts = datetime.strptime(f.stem, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
            if ts < cutoff:
                f.unlink()
        except ValueError:
            pass
