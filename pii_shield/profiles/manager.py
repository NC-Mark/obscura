"""
Profile manager for PII Shield.

Profiles let users save named configurations combining domain settings,
extra stoplist terms, custom regex patterns, and detection thresholds.

Stored as JSON files in ~/.pii_shield/profiles/<name>.json

Profile schema:
{
  "name":            "credit_desk",          required
  "description":     "UK credit trading",   optional
  "base_domain":     "financial",            optional — default "general"
  "extra_stoplist":  ["Delta", "Gamma"],     optional — merged with domain stoplist
  "custom_patterns": [                       optional — same format as entities.json
    {
      "name":    "INTERNAL_ACCOUNT",
      "pattern": "ACC\\d{8}",
      "score":   0.9,
      "context": ["account", "client account"]
    }
  ],
  "min_score":    0.55,                      optional — overrides global setting
  "gliner_model": null                       optional — override GLiNER model for this profile
}

Usage:
    from pii_shield.profiles import save_profile, resolve_profile

    save_profile({
        "name": "oncology",
        "base_domain": "healthcare",
        "extra_stoplist": ["ECOG", "RECIST", "PFS"],
    })

    ctx = resolve_profile("oncology")
    # ctx.domain, ctx.extra_stoplist, ctx.min_score, ctx.custom_patterns
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..config import PROFILES_DIR

log = logging.getLogger("pii-shield.profiles")


@dataclass
class ProfileContext:
    """Resolved profile ready for use by the engine."""
    name:             str
    domain:           str              = "general"
    extra_stoplist:   frozenset        = field(default_factory=frozenset)
    custom_patterns:  list             = field(default_factory=list)
    min_score:        Optional[float]  = None
    gliner_model:     Optional[str]    = None
    description:      str              = ""


# ── CRUD ──────────────────────────────────────────────────────────────────────

def save_profile(profile: dict) -> str:
    """Validate and save a profile. Returns the file path."""
    name = profile.get("name", "").strip()
    if not name:
        raise ValueError("Profile must have a 'name' field.")

    # Sanitise name for use as filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = PROFILES_DIR / f"{safe_name}.json"

    # Ensure required defaults
    profile.setdefault("base_domain", "general")
    profile.setdefault("extra_stoplist", [])
    profile.setdefault("custom_patterns", [])

    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Profile saved: {name} → {path}")
    return str(path)


def load_profile(name: str) -> dict | None:
    """Load a profile by name. Returns None if not found."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = PROFILES_DIR / f"{safe_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Failed to load profile '{name}': {e}")
        return None


def list_profiles() -> list[dict]:
    """Return all saved profiles as a list of dicts."""
    profiles = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            profiles.append({
                "name":        data.get("name", p.stem),
                "description": data.get("description", ""),
                "base_domain": data.get("base_domain", "general"),
                "extra_stoplist_count": len(data.get("extra_stoplist", [])),
                "custom_patterns_count": len(data.get("custom_patterns", [])),
                "min_score":   data.get("min_score"),
            })
        except Exception:
            pass
    return profiles


def delete_profile(name: str) -> bool:
    """Delete a profile. Returns True if deleted, False if not found."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = PROFILES_DIR / f"{safe_name}.json"
    if path.exists():
        path.unlink()
        log.info(f"Profile deleted: {name}")
        return True
    return False


def resolve_profile(name: str) -> ProfileContext | None:
    """Load a profile and return a ProfileContext ready for use by the engine.
    Returns None if the profile does not exist.
    """
    data = load_profile(name)
    if data is None:
        return None

    min_score = data.get("min_score")
    if min_score is not None:
        min_score = float(min_score)

    return ProfileContext(
        name            = data.get("name", name),
        domain          = data.get("base_domain", "general"),
        extra_stoplist  = frozenset(t.lower() for t in data.get("extra_stoplist", [])),
        custom_patterns = data.get("custom_patterns", []),
        min_score       = min_score,
        gliner_model    = data.get("gliner_model"),
        description     = data.get("description", ""),
    )
