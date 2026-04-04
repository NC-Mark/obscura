"""
Domain stoplists for PII false-positive filtering.

Usage:
    from pii_shield.stoplists import get_stoplist
    terms = get_stoplist("financial")   # returns frozenset
    terms = get_stoplist("all")         # merged across all domains
"""

from .legal import LEGAL_STOPLIST
from .financial import FINANCIAL_STOPLIST
from .healthcare import HEALTHCARE_STOPLIST

_ALL = LEGAL_STOPLIST | FINANCIAL_STOPLIST | HEALTHCARE_STOPLIST

_MAP = {
    "legal":      LEGAL_STOPLIST,
    "financial":  FINANCIAL_STOPLIST,
    "healthcare": HEALTHCARE_STOPLIST,
    "general":    _ALL,
    "all":        _ALL,
}


def get_stoplist(domain: str = "general") -> frozenset:
    """Return the stoplist for the given domain name (case-insensitive)."""
    return _MAP.get(domain.lower(), _ALL)


__all__ = ["get_stoplist", "LEGAL_STOPLIST", "FINANCIAL_STOPLIST", "HEALTHCARE_STOPLIST"]
