"""
PII Shield — Privacy middleware for LLM workflows.

Anonymize PII in documents before sending to any LLM.
Restore real values after processing.
Supports legal, financial, and healthcare domains.

Original work by Grigorii Moskalev (MIT License).
Extended with domain-specific stoplists, recognizers, parallel processing,
GPU support, and standalone REST API.
"""

from .engine.core import PIIEngine
from .config import Domain

__all__ = ["PIIEngine", "Domain"]
__version__ = "7.0.0"
