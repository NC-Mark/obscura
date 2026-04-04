"""
Custom user terms loader for PII Shield.

Loads three sources of user-supplied terms:

1. ~/.pii_shield/custom/stoplist.txt
   One term per line (UTF-8). These are NEVER anonymized regardless of domain.
   Example lines:
       Alpha Growth Fund
       Prime Brokerage Desk
       Dr. Smith           ← if you never want a specific name anonymized

2. ~/.pii_shield/custom/entities.json
   Array of custom Presidio pattern recognizers. Each entry:
   {
     "name":     "INTERNAL_ACCOUNT",   required — entity type tag
     "pattern":  "ACC\\d{8}",          required — Python regex
     "score":    0.9,                  optional — default 0.7
     "context":  ["account", "acct"],  optional — boosts score when nearby
     "language": "en"                  optional — default "en"
   }

3. ~/.pii_shield/learned_stoplist.json
   Auto-saved when user removes a false positive in the HITL review UI.
   Structure: {"financial": ["Delta", "Gamma"], "general": [], ...}
   Never edit manually — managed by the review server.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import CUSTOM_DIR, LEARNED_STOPLIST_FILE

log = logging.getLogger("pii-shield.custom")

_STOPLIST_FILE = CUSTOM_DIR / "stoplist.txt"
_ENTITIES_FILE = CUSTOM_DIR / "entities.json"


# ── Custom stoplist ───────────────────────────────────────────────────────────

def load_custom_stoplist() -> frozenset:
    """Load ~/.pii_shield/custom/stoplist.txt. Returns frozenset of lowercase terms."""
    if not _STOPLIST_FILE.exists():
        return frozenset()
    try:
        terms = set()
        for line in _STOPLIST_FILE.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t and not t.startswith("#"):
                terms.add(t.lower())
        log.info(f"Custom stoplist: {len(terms)} terms from {_STOPLIST_FILE}")
        return frozenset(terms)
    except Exception as e:
        log.warning(f"Failed to load custom stoplist: {e}")
        return frozenset()


# ── Learned stoplist (HITL feedback) ─────────────────────────────────────────

def load_learned_stoplist(domain: str = "general") -> frozenset:
    """Load HITL-learned false positives for the given domain."""
    if not LEARNED_STOPLIST_FILE.exists():
        return frozenset()
    try:
        data: dict = json.loads(LEARNED_STOPLIST_FILE.read_text(encoding="utf-8"))
        terms = set()
        # Always include general terms + domain-specific terms
        for d in ("general", domain):
            for t in data.get(d, []):
                terms.add(t.lower())
        if terms:
            log.info(f"Learned stoplist: {len(terms)} terms for domain={domain}")
        return frozenset(terms)
    except Exception as e:
        log.warning(f"Failed to load learned stoplist: {e}")
        return frozenset()


def save_learned_term(term: str, domain: str = "general"):
    """Append a term to the learned stoplist for the given domain.
    Called automatically when a user removes a false positive in the review UI.
    """
    if not term or not term.strip():
        return
    term = term.strip().lower()
    try:
        data: dict = {}
        if LEARNED_STOPLIST_FILE.exists():
            data = json.loads(LEARNED_STOPLIST_FILE.read_text(encoding="utf-8"))
        bucket = data.setdefault(domain, [])
        if term not in bucket:
            bucket.append(term)
            LEARNED_STOPLIST_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info(f"Learned stoplist: added '{term}' to domain={domain}")
    except Exception as e:
        log.warning(f"Failed to save learned term '{term}': {e}")


# ── Custom pattern recognizers ────────────────────────────────────────────────

def load_custom_patterns() -> list[dict]:
    """Load ~/.pii_shield/custom/entities.json.
    Returns list of pattern dicts ready for register_custom_patterns().
    """
    if not _ENTITIES_FILE.exists():
        return []
    try:
        patterns = json.loads(_ENTITIES_FILE.read_text(encoding="utf-8"))
        if not isinstance(patterns, list):
            log.warning(f"entities.json must be a JSON array — got {type(patterns)}")
            return []
        valid = []
        for i, p in enumerate(patterns):
            if not isinstance(p, dict):
                log.warning(f"entities.json item {i}: expected dict, skipping")
                continue
            if "name" not in p or "pattern" not in p:
                log.warning(f"entities.json item {i}: missing 'name' or 'pattern', skipping")
                continue
            valid.append(p)
        log.info(f"Custom patterns: {len(valid)} recognizers from {_ENTITIES_FILE}")
        return valid
    except Exception as e:
        log.warning(f"Failed to load custom patterns: {e}")
        return []


def register_custom_patterns(analyzer, patterns: list[dict]) -> int:
    """Register custom patterns from entities.json with a Presidio AnalyzerEngine."""
    from presidio_analyzer import PatternRecognizer, Pattern
    count = 0
    for p in patterns:
        try:
            recognizer = PatternRecognizer(
                supported_entity=p["name"],
                supported_language=p.get("language", "en"),
                patterns=[Pattern(
                    name=p["name"].lower(),
                    regex=p["pattern"],
                    score=float(p.get("score", 0.7)),
                )],
                context=p.get("context", []),
            )
            analyzer.registry.add_recognizer(recognizer)
            count += 1
        except Exception as e:
            log.warning(f"Failed to register custom pattern '{p.get('name')}': {e}")
    return count


# ── Combined stoplist (for engine) ───────────────────────────────────────────

def get_combined_stoplist(domain_stoplist: frozenset, domain: str = "general") -> frozenset:
    """Merge domain stoplist + user custom stoplist + learned stoplist."""
    custom   = load_custom_stoplist()
    learned  = load_learned_stoplist(domain)
    combined = domain_stoplist | custom | learned
    log.info(f"Combined stoplist: {len(domain_stoplist)} domain + "
             f"{len(custom)} custom + {len(learned)} learned = {len(combined)} total")
    return combined
