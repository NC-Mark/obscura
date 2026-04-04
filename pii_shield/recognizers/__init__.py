"""
Custom Presidio pattern recognizers for PII Shield.
"""

from .eu_recognizers import register_eu_recognizers
from .financial_recognizers import register_financial_recognizers
from .healthcare_recognizers import register_healthcare_recognizers


def register_all_recognizers(analyzer, domain: str = "general"):
    """Register recognizers appropriate for the given domain."""
    count = 0
    count += register_eu_recognizers(analyzer)

    domain = domain.lower()
    if domain in ("financial", "general", "all"):
        count += register_financial_recognizers(analyzer)
    if domain in ("healthcare", "general", "all"):
        count += register_healthcare_recognizers(analyzer)

    return count


__all__ = [
    "register_eu_recognizers",
    "register_financial_recognizers",
    "register_healthcare_recognizers",
    "register_all_recognizers",
]
