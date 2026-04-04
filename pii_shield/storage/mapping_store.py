"""
Mapping persistence for PII Shield.

Mappings are stored:
  - On disk: ~/.pii_shield/mappings/<session_id>.json  (TTL-cleaned)
  - In memory: bounded LRU cache (prevents unbounded growth in long-running server)

Review data (for HITL) lives alongside mappings as review_<session_id>.json.
"""

import json
import logging
import time
from collections import OrderedDict
from pathlib import Path

from ..config import MAPPING_DIR, MAPPING_TTL_DAYS

log = logging.getLogger("pii-shield.storage")

# ── Bounded in-memory cache ───────────────────────────────────────────────────
# Prevents the unbounded dict growth that existed in the original code.
_MAX_CACHE = 200
_cache: OrderedDict = OrderedDict()    # session_id → data dict
_review_cache: OrderedDict = OrderedDict()  # session_id → review dict


def _cache_put(cache: OrderedDict, key: str, value: dict):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _MAX_CACHE:
        cache.popitem(last=False)


def _cache_get(cache: OrderedDict, key: str):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    return None


# ── Mapping save / load ───────────────────────────────────────────────────────

def save_mapping(session_id: str, mapping: dict, metadata: dict = None) -> str:
    """Persist mapping to disk + memory. Returns storage path."""
    data = {
        "session_id": session_id,
        "mapping": mapping,
        "metadata": metadata or {},
        "timestamp": time.time(),
    }
    _cache_put(_cache, session_id, data)

    try:
        MAPPING_DIR.mkdir(parents=True, exist_ok=True)
        path = MAPPING_DIR / f"{session_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return str(path)
    except Exception as e:
        log.warning(f"save_mapping disk write failed (memory OK): {e}")
        return f"memory://{session_id}"


def load_mapping(session_id: str) -> dict:
    """Load mapping. Tries disk first, then memory cache."""
    try:
        path = MAPPING_DIR / f"{session_id}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            _cache_put(_cache, session_id, data)
            return data.get("mapping", {})
    except Exception as e:
        log.warning(f"load_mapping disk read failed: {e}")

    cached = _cache_get(_cache, session_id)
    if cached:
        return cached.get("mapping", {})
    return {}


def latest_session_id() -> str:
    """Return session_id of the most recently created mapping."""
    try:
        files = sorted(
            (f for f in MAPPING_DIR.glob("*.json") if not f.name.startswith("review_")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return json.loads(files[0].read_text(encoding="utf-8")).get("session_id", "")
    except Exception:
        pass
    if _cache:
        newest = max(_cache.values(), key=lambda d: d.get("timestamp", 0))
        return newest.get("session_id", "")
    return ""


def cleanup_old_mappings():
    """Delete mapping files older than TTL. Also prunes review files."""
    cutoff = time.time() - (MAPPING_TTL_DAYS * 86400)
    removed = 0
    for f in MAPPING_DIR.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed:
        log.info(f"Cleaned {removed} expired mappings (>{MAPPING_TTL_DAYS}d)")


# ── Review data save / load ───────────────────────────────────────────────────

def save_review(session_id: str, review_data: dict):
    """Persist HITL review data to disk + memory."""
    _cache_put(_review_cache, session_id, review_data)
    try:
        path = MAPPING_DIR / f"review_{session_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(review_data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        log.warning(f"save_review disk write failed (memory OK): {e}")


def load_review(session_id: str) -> dict | None:
    """Load review data from disk."""
    try:
        path = MAPPING_DIR / f"review_{session_id}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            _cache_put(_review_cache, session_id, data)
            return data
    except Exception as e:
        log.warning(f"load_review disk read failed: {e}")
    return None


def get_review(session_id: str) -> dict | None:
    """Get review data: memory first, then disk."""
    cached = _cache_get(_review_cache, session_id)
    if cached:
        return cached
    return load_review(session_id)
