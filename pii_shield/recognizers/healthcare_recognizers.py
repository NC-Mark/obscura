"""
Healthcare / clinical PII pattern recognizers for Presidio.

Detects:
  NPI              — National Provider Identifier (US, 10 digits)
  DEA_NUMBER       — DEA registration number (letter + letter + 7 digits)
  MEDICARE_ID      — Medicare Beneficiary Identifier (11 alphanumeric)
  MEDICAL_RECORD_NUMBER — Generic MRN (context-triggered)
  MEDICAL_LICENSE  — State medical license numbers
"""

from presidio_analyzer import PatternRecognizer, Pattern


def register_healthcare_recognizers(analyzer) -> int:
    recognizers = _build_recognizers()
    for rec in recognizers:
        analyzer.registry.add_recognizer(rec)
    return len(recognizers)


def _build_recognizers():
    recognizers = []

    # ── NPI (National Provider Identifier) ───────────────────────────────────
    # 10-digit number starting with 1 or 2 (individual vs organisation).
    recognizers.append(PatternRecognizer(
        supported_entity="NPI",
        supported_language="en",
        patterns=[
            Pattern("npi_full", r"\b[12]\d{9}\b", 0.5),
        ],
        context=["NPI", "national provider identifier", "provider number",
                 "provider ID", "physician NPI", "billing NPI", "Type 1 NPI", "Type 2 NPI"],
    ))

    # ── DEA Registration Number ───────────────────────────────────────────────
    # Format: registrant-type letter + last-name letter + 7 digits.
    # First letter codes: A/B/C/D/E/F/G/H/J/K/L/M/P/R/S/T/U/X
    recognizers.append(PatternRecognizer(
        supported_entity="DEA_NUMBER",
        supported_language="en",
        patterns=[
            Pattern("dea_full", r"\b[ABCDEFGHJKLMNPRSTUXabcdefghjklmnprstux][A-Za-z9]\d{7}\b", 0.7),
        ],
        context=["DEA", "DEA number", "DEA registration", "drug enforcement",
                 "controlled substance", "Schedule II", "Schedule III",
                 "prescriber DEA", "DEA license"],
    ))

    # ── Medicare Beneficiary Identifier (MBI) ─────────────────────────────────
    # New MBI format (since 2018): 1 letter + 1 digit + 1 letter/digit +
    # 1 digit + 1 letter + 1 letter/digit + 1 digit + 1 letter + 1 letter/digit +
    # 1 letter/digit + 1 digit = 11 characters.
    # Pattern: C[A-Z0-9][A-Z][A-Z0-9]{3}[A-Z][A-Z0-9]{2}[A-Z0-9]\d (simplified)
    recognizers.append(PatternRecognizer(
        supported_entity="MEDICARE_ID",
        supported_language="en",
        patterns=[
            # Simplified: 1 letter + 10 alphanumeric (excluding S, L, O, I, B, Z)
            Pattern("mbi_new",  r"\b[A-HJ-NP-RT-Z][A-Z0-9]{10}\b", 0.4),
            # Old HIC / HICN: 9-digit SSN-based (deprecated but still in some records)
            Pattern("hicn_old", r"\b\d{9}[A-Z]\b", 0.2),
        ],
        context=["Medicare", "Medicare ID", "MBI", "beneficiary identifier",
                 "Medicare number", "Medicare beneficiary", "CMS", "HICN"],
    ))

    # ── Medical Record Number (MRN) ───────────────────────────────────────────
    # Highly facility-specific. Use context-triggered pattern only.
    recognizers.append(PatternRecognizer(
        supported_entity="MEDICAL_RECORD_NUMBER",
        supported_language="en",
        patterns=[
            Pattern("mrn_numeric",  r"\b\d{6,10}\b", 0.1),    # needs strong context
            Pattern("mrn_prefixed", r"\bMRN[-:\s]?\d{5,10}\b", 0.8),
            Pattern("mrn_prefixed2",r"\bMR[-:\s]?\d{5,10}\b",  0.7),
        ],
        context=["MRN", "medical record", "medical record number", "patient ID",
                 "patient number", "chart number", "encounter number",
                 "hospital number", "registration number"],
    ))

    # ── State Medical License ─────────────────────────────────────────────────
    # US state medical licenses vary by state. Common patterns:
    # 2-letter state prefix + 5-8 digits, or just letters + digits.
    recognizers.append(PatternRecognizer(
        supported_entity="MEDICAL_LICENSE",
        supported_language="en",
        patterns=[
            Pattern("med_lic_state",   r"\b[A-Z]{2}\d{5,8}\b", 0.3),
            Pattern("med_lic_generic", r"\b[A-Z]\d{6,8}\b",    0.2),
        ],
        context=["medical license", "license number", "state license",
                 "physician license", "medical board", "licensure",
                 "DEA license", "nursing license"],
    ))

    return recognizers
