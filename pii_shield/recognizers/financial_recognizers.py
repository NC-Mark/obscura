"""
Financial markets PII pattern recognizers for Presidio.

Detects:
  LEI      — Legal Entity Identifier (20-char alphanumeric)
  ISIN     — International Securities ID (2-letter country + 9 alphanum + check)
  CUSIP    — Committee on Uniform Securities ID (8 alphanum + check digit)
  SWIFT_BIC — SWIFT / BIC code (8 or 11 chars)
  FINANCIAL_ACCOUNT — Generic account number (context-triggered)
"""

from presidio_analyzer import PatternRecognizer, Pattern


def register_financial_recognizers(analyzer) -> int:
    recognizers = _build_recognizers()
    for rec in recognizers:
        analyzer.registry.add_recognizer(rec)
    return len(recognizers)


def _build_recognizers():
    recognizers = []

    # ── LEI (Legal Entity Identifier) ─────────────────────────────────────────
    # 20-character alphanumeric. First 4 = registrar prefix, chars 5-18 = entity,
    # last 2 = check digits (ISO 17442).
    recognizers.append(PatternRecognizer(
        supported_entity="LEI",
        supported_language="en",
        patterns=[
            Pattern("lei_full", r"\b[A-Z0-9]{18}\d{2}\b", 0.6),
        ],
        context=["LEI", "legal entity identifier", "GLEIF", "entity identifier",
                 "counterparty LEI", "reporting entity"],
    ))

    # ── ISIN (International Securities Identification Number) ─────────────────
    # 2 uppercase letters (country) + 9 alphanumeric + 1 check digit = 12 chars.
    recognizers.append(PatternRecognizer(
        supported_entity="ISIN",
        supported_language="en",
        patterns=[
            Pattern("isin_full", r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b", 0.65),
        ],
        context=["ISIN", "international securities", "securities identifier",
                 "instrument code", "security code", "bond", "equity", "stock"],
    ))

    # ── CUSIP ─────────────────────────────────────────────────────────────────
    # 9 characters: 6 alphanumeric (issuer) + 2 alphanumeric (issue) + 1 check.
    recognizers.append(PatternRecognizer(
        supported_entity="CUSIP",
        supported_language="en",
        patterns=[
            Pattern("cusip_full", r"\b[A-Z0-9]{8}[0-9]\b", 0.55),
        ],
        context=["CUSIP", "committee on uniform securities", "security identifier",
                 "US security", "bond identifier"],
    ))

    # ── SWIFT / BIC ───────────────────────────────────────────────────────────
    # Bank Identifier Code: 4-letter bank + 2-letter country + 2-char location
    # + optional 3-char branch = 8 or 11 characters.
    recognizers.append(PatternRecognizer(
        supported_entity="SWIFT_BIC",
        supported_language="en",
        patterns=[
            Pattern("bic_11", r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}[A-Z0-9]{3}\b", 0.75),
            Pattern("bic_8",  r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}\b", 0.6),
        ],
        context=["SWIFT", "BIC", "bank identifier", "SWIFT code", "routing",
                 "correspondent bank", "wire transfer", "SEPA", "intermediary bank"],
    ))

    # ── Financial Account Number ──────────────────────────────────────────────
    # Generic account number patterns — requires strong context to avoid false positives.
    # Covers common formats: 8-12 digit account numbers, hyphenated variants.
    recognizers.append(PatternRecognizer(
        supported_entity="FINANCIAL_ACCOUNT",
        supported_language="en",
        patterns=[
            Pattern("acct_numeric",    r"\b\d{8,12}\b", 0.1),       # needs context
            Pattern("acct_hyphenated", r"\b\d{4}-\d{4}-\d{4}\b", 0.5),
            Pattern("acct_sort_uk",    r"\b\d{2}-\d{2}-\d{2}\b", 0.3),   # UK sort code
        ],
        context=["account number", "account no", "acct no", "account #",
                 "client account", "brokerage account", "portfolio account",
                 "sort code", "routing number", "transit number",
                 "custodian account", "omnibus account"],
    ))

    return recognizers
