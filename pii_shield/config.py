"""
Global configuration and constants for PII Shield.
"""

import json
import os
from enum import Enum
from pathlib import Path


# ── Domain selection ──────────────────────────────────────────────────────────

class Domain(str, Enum):
    LEGAL = "legal"
    FINANCIAL = "financial"
    HEALTHCARE = "healthcare"
    GENERAL = "general"   # all stoplists combined


# ── Available GLiNER models ───────────────────────────────────────────────────

GLINER_MODELS = {
    "small": {
        "id":    "urchade/gliner_small-v2.1",
        "size":  "~170 MB",
        "desc":  "Fast, good quality — recommended default",
    },
    "medium": {
        "id":    "urchade/gliner_medium-v2.1",
        "size":  "~340 MB",
        "desc":  "Better accuracy on ambiguous names, moderate speed",
    },
    "large": {
        "id":    "urchade/gliner_large-v2.1",
        "size":  "~680 MB",
        "desc":  "Best accuracy, slower — use if quality is critical",
    },
    "multilingual": {
        "id":    "urchade/gliner_multi-v2.1",
        "size":  "~340 MB",
        "desc":  "Multi-language support (EN + EU languages)",
    },
}

DEFAULT_GLINER_MODEL = "urchade/gliner_small-v2.1"


# ── User config file: ~/.pii_shield/config.json ───────────────────────────────
# Persists user choices across sessions (GLiNER model, default domain, etc.)
# Env vars take precedence over config file values.

PII_SHIELD_DIR = Path.home() / ".pii_shield"
USER_CONFIG_FILE = PII_SHIELD_DIR / "config.json"

_user_config: dict = {}
try:
    if USER_CONFIG_FILE.exists():
        _user_config = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
except Exception:
    pass


def save_user_config(updates: dict):
    """Merge updates into ~/.pii_shield/config.json and reload."""
    global _user_config
    PII_SHIELD_DIR.mkdir(parents=True, exist_ok=True)
    _user_config.update(updates)
    USER_CONFIG_FILE.write_text(
        json.dumps(_user_config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _cfg(key: str, env_var: str, default):
    """Resolve: env var > config file > default."""
    if env_var in os.environ:
        return os.environ[env_var]
    return _user_config.get(key, default)


# ── NER model ─────────────────────────────────────────────────────────────────

def get_gliner_model() -> str:
    """Return the configured GLiNER model ID (env > config.json > default)."""
    return _cfg("gliner_model", "PII_GLINER_MODEL", DEFAULT_GLINER_MODEL)

# Module-level alias for backward compat
GLINER_MODEL = get_gliner_model()

# ── Detection thresholds ──────────────────────────────────────────────────────

DEFAULT_MIN_SCORE = 0.50

def get_min_score() -> float:
    val = _cfg("min_score", "PII_MIN_SCORE", DEFAULT_MIN_SCORE)
    return float(val)


# ── Mapping persistence ────────────────────────────────────────────────────────

MAPPING_TTL_DAYS = int(_cfg("mapping_ttl_days", "PII_MAPPING_TTL_DAYS", "7"))
MAPPING_DIR = PII_SHIELD_DIR / "mappings"
AUDIT_DIR   = PII_SHIELD_DIR / "audit"

# ── Custom user terms ─────────────────────────────────────────────────────────
# Users drop files here to extend/override detection behaviour.
#
#   ~/.pii_shield/custom/stoplist.txt     — one term per line, never anonymize
#   ~/.pii_shield/custom/entities.json    — custom regex recognizers
#   ~/.pii_shield/learned_stoplist.json   — auto-saved from HITL review FP removals

CUSTOM_DIR           = PII_SHIELD_DIR / "custom"
LEARNED_STOPLIST_FILE = PII_SHIELD_DIR / "learned_stoplist.json"

# ── Profiles ──────────────────────────────────────────────────────────────────
# Named profiles stored as JSON in ~/.pii_shield/profiles/<name>.json
# Each combines domain + extra stoplist + custom patterns + optional settings.

PROFILES_DIR = PII_SHIELD_DIR / "profiles"

try:
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


# ── Status file (for MCP bootstrap monitoring) ────────────────────────────────

STATUS_DIR  = PII_SHIELD_DIR
STATUS_FILE = STATUS_DIR / "status.json"


# ── Review server ─────────────────────────────────────────────────────────────

REVIEW_PORT = int(os.environ.get("PII_REVIEW_PORT", "8766"))

# ── REST API ──────────────────────────────────────────────────────────────────

API_HOST = os.environ.get("PII_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("PII_API_PORT", "8080"))

# ── Entity types ──────────────────────────────────────────────────────────────

SUPPORTED_ENTITIES = [
    # NER-based (GLiNER)
    "PERSON", "ORGANIZATION", "LOCATION", "NRP",
    # Pattern-based (Presidio built-in)
    "EMAIL_ADDRESS", "PHONE_NUMBER", "URL", "IP_ADDRESS",
    "CREDIT_CARD", "IBAN_CODE", "CRYPTO",
    "US_SSN", "US_PASSPORT", "US_DRIVER_LICENSE",
    # EU recognizers
    "UK_NHS", "UK_NIN", "UK_PASSPORT", "UK_CRN", "UK_DRIVING_LICENCE",
    "EU_VAT", "EU_PASSPORT",
    "DE_TAX_ID", "DE_SOCIAL_SECURITY",
    "FR_NIR", "FR_CNI",
    "IT_FISCAL_CODE", "IT_VAT",
    "ES_DNI", "ES_NIE",
    "CY_TIC", "CY_ID_CARD",
    # Financial recognizers
    "LEI", "ISIN", "CUSIP", "SWIFT_BIC",
    "FINANCIAL_ACCOUNT",
    # Healthcare recognizers
    "NPI", "DEA_NUMBER", "MEDICARE_ID", "MEDICAL_RECORD_NUMBER",
    "MEDICAL_LICENSE",
]

# Short tag names used inside placeholders: <PERSON_1>, <ORG_2>, etc.
TAG_NAMES = {
    "PERSON": "PERSON", "ORGANIZATION": "ORG", "LOCATION": "LOCATION",
    "NRP": "NRP",
    "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "URL": "URL",
    "IP_ADDRESS": "IP", "CREDIT_CARD": "CREDIT_CARD", "IBAN_CODE": "IBAN",
    "CRYPTO": "CRYPTO",
    "US_SSN": "US_SSN", "US_PASSPORT": "US_PASSPORT", "US_DRIVER_LICENSE": "US_DL",
    "UK_NHS": "UK_NHS", "UK_NIN": "UK_NIN", "UK_PASSPORT": "UK_PASSPORT",
    "UK_CRN": "UK_CRN", "UK_DRIVING_LICENCE": "UK_DL",
    "EU_VAT": "EU_VAT", "EU_PASSPORT": "EU_PASSPORT",
    "DE_TAX_ID": "DE_TAX", "DE_SOCIAL_SECURITY": "DE_SSN",
    "FR_NIR": "FR_NIR", "FR_CNI": "FR_CNI",
    "IT_FISCAL_CODE": "IT_CF", "IT_VAT": "IT_VAT",
    "ES_DNI": "ES_DNI", "ES_NIE": "ES_NIE",
    "CY_TIC": "CY_TIC", "CY_ID_CARD": "CY_ID",
    "MEDICAL_LICENSE": "MED_LIC",
    # Financial
    "LEI": "LEI", "ISIN": "ISIN", "CUSIP": "CUSIP", "SWIFT_BIC": "SWIFT",
    "FINANCIAL_ACCOUNT": "ACCT",
    # Healthcare
    "NPI": "NPI", "DEA_NUMBER": "DEA", "MEDICARE_ID": "MEDICARE",
    "MEDICAL_RECORD_NUMBER": "MRN",
}

# Entity types that are proper-noun based (subject to stoplist / lowercase filtering)
NAMED_ENTITY_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "NRP"}

# Pattern-based types that can be noisy — apply extra stoplist filtering
NOISY_PATTERN_TYPES = {
    "DE_SOCIAL_SECURITY", "EU_VAT", "UK_DRIVING_LICENCE",
    "MEDICAL_LICENSE", "NRP",
}
