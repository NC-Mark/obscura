"""
European PII Recognizers for Presidio.
Original work by Grigorii Moskalev. Moved to recognizers package.
"""

from presidio_analyzer import PatternRecognizer, Pattern


def register_eu_recognizers(analyzer) -> int:
    recognizers = _build_recognizers()
    for rec in recognizers:
        analyzer.registry.add_recognizer(rec)
    return len(recognizers)


def _build_recognizers():
    recognizers = []

    # UK National Insurance Number
    recognizers.append(PatternRecognizer(
        supported_entity="UK_NIN", supported_language="en",
        patterns=[Pattern("uk_nin_spaced", r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", 0.7)],
        context=["national insurance", "NI number", "NIN", "NINO", "tax", "HMRC", "PAYE"],
    ))

    # UK Passport
    recognizers.append(PatternRecognizer(
        supported_entity="UK_PASSPORT", supported_language="en",
        patterns=[Pattern("uk_passport", r"\b\d{9}\b", 0.1)],
        context=["passport", "travel document", "UK passport", "HM Passport", "HMPO"],
    ))

    # UK Company Registration Number
    recognizers.append(PatternRecognizer(
        supported_entity="UK_CRN", supported_language="en",
        patterns=[
            Pattern("uk_crn_numeric", r"\b\d{8}\b", 0.1),
            Pattern("uk_crn_alpha",   r"\b[A-Z]{2}\d{6}\b", 0.4),
        ],
        context=["company number", "registration number", "Companies House", "CRN", "registered number"],
    ))

    # UK Driving Licence
    recognizers.append(PatternRecognizer(
        supported_entity="UK_DRIVING_LICENCE", supported_language="en",
        patterns=[Pattern("uk_dl", r"\b[A-Z]{5}\d{6}[A-Z0-9]{2}\d{2}[A-Z]{2}\b", 0.75)],
        context=["driving licence", "driver's licence", "DVLA", "driving license"],
    ))

    # UK NHS Number (10 digits, space-separated: NNN NNN NNNN)
    recognizers.append(PatternRecognizer(
        supported_entity="UK_NHS", supported_language="en",
        patterns=[Pattern("uk_nhs", r"\b\d{3}\s?\d{3}\s?\d{4}\b", 0.5)],
        context=["NHS number", "NHS", "national health", "patient number"],
    ))

    # German Tax ID
    recognizers.append(PatternRecognizer(
        supported_entity="DE_TAX_ID", supported_language="en",
        patterns=[Pattern("de_tax_id", r"\b\d{11}\b", 0.1)],
        context=["Steuer-ID", "Steueridentifikationsnummer", "tax identification", "IdNr", "TIN", "Finanzamt"],
    ))

    # German Social Security
    recognizers.append(PatternRecognizer(
        supported_entity="DE_SOCIAL_SECURITY", supported_language="en",
        patterns=[Pattern("de_sv", r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{2}\s?\d\b", 0.6)],
        context=["Sozialversicherungsnummer", "SV-Nummer", "social security", "Rentenversicherung"],
    ))

    # French NIR / INSEE
    recognizers.append(PatternRecognizer(
        supported_entity="FR_NIR", supported_language="en",
        patterns=[Pattern("fr_nir", r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b", 0.65)],
        context=["NIR", "INSEE", "sécurité sociale", "social security", "carte vitale"],
    ))

    # French CNI
    recognizers.append(PatternRecognizer(
        supported_entity="FR_CNI", supported_language="en",
        patterns=[Pattern("fr_cni", r"\b\d{12}\b", 0.1)],
        context=["carte nationale", "CNI", "national identity", "carte d'identité"],
    ))

    # Italian Codice Fiscale
    recognizers.append(PatternRecognizer(
        supported_entity="IT_FISCAL_CODE", supported_language="en",
        patterns=[Pattern("it_cf", r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b", 0.8)],
        context=["codice fiscale", "fiscal code", "CF", "Italian tax"],
    ))

    # Italian VAT
    recognizers.append(PatternRecognizer(
        supported_entity="IT_VAT", supported_language="en",
        patterns=[Pattern("it_vat", r"\bIT\s?\d{11}\b", 0.75)],
        context=["partita IVA", "VAT", "P.IVA"],
    ))

    # Spanish DNI
    recognizers.append(PatternRecognizer(
        supported_entity="ES_DNI", supported_language="en",
        patterns=[Pattern("es_dni", r"\b\d{8}[A-Z]\b", 0.6)],
        context=["DNI", "documento nacional", "NIF", "Spanish ID"],
    ))

    # Spanish NIE
    recognizers.append(PatternRecognizer(
        supported_entity="ES_NIE", supported_language="en",
        patterns=[Pattern("es_nie", r"\b[XYZ]\d{7}[A-Z]\b", 0.7)],
        context=["NIE", "número de identidad de extranjero", "Spanish residence"],
    ))

    # Cyprus TIC
    recognizers.append(PatternRecognizer(
        supported_entity="CY_TIC", supported_language="en",
        patterns=[Pattern("cy_tic", r"\b\d{8}[A-Z]\b", 0.5)],
        context=["TIC", "tax identification", "Cyprus tax", "αριθμός φορολογικού"],
    ))

    # Cyprus ID Card
    recognizers.append(PatternRecognizer(
        supported_entity="CY_ID_CARD", supported_language="en",
        patterns=[Pattern("cy_id", r"\b\d{6,8}\b", 0.05)],
        context=["Cyprus ID", "identity card", "ARC number", "ταυτότητα"],
    ))

    # EU VAT
    eu_vat_patterns = [
        Pattern("vat_at", r"\bATU\d{8}\b", 0.8),
        Pattern("vat_be", r"\bBE[01]\d{9}\b", 0.8),
        Pattern("vat_bg", r"\bBG\d{9,10}\b", 0.8),
        Pattern("vat_cy", r"\bCY\d{8}[A-Z]\b", 0.8),
        Pattern("vat_cz", r"\bCZ\d{8,10}\b", 0.8),
        Pattern("vat_de", r"\bDE\d{9}\b", 0.8),
        Pattern("vat_dk", r"\bDK\d{8}\b", 0.8),
        Pattern("vat_ee", r"\bEE\d{9}\b", 0.8),
        Pattern("vat_es", r"\bES[A-Z0-9]\d{7}[A-Z0-9]\b", 0.8),
        Pattern("vat_fi", r"\bFI\d{8}\b", 0.8),
        Pattern("vat_fr", r"\bFR[A-Z0-9]{2}\d{9}\b", 0.8),
        Pattern("vat_el", r"\bEL\d{9}\b", 0.8),
        Pattern("vat_hr", r"\bHR\d{11}\b", 0.8),
        Pattern("vat_hu", r"\bHU\d{8}\b", 0.8),
        Pattern("vat_ie", r"\bIE\d[A-Z0-9+*]\d{5}[A-Z]\b", 0.8),
        Pattern("vat_it", r"\bIT\d{11}\b", 0.8),
        Pattern("vat_lt", r"\bLT\d{9,12}\b", 0.8),
        Pattern("vat_lu", r"\bLU\d{8}\b", 0.8),
        Pattern("vat_lv", r"\bLV\d{11}\b", 0.8),
        Pattern("vat_mt", r"\bMT\d{8}\b", 0.8),
        Pattern("vat_nl", r"\bNL\d{9}B\d{2}\b", 0.8),
        Pattern("vat_pl", r"\bPL\d{10}\b", 0.8),
        Pattern("vat_pt", r"\bPT\d{9}\b", 0.8),
        Pattern("vat_ro", r"\bRO\d{2,10}\b", 0.7),
        Pattern("vat_se", r"\bSE\d{12}\b", 0.8),
        Pattern("vat_si", r"\bSI\d{8}\b", 0.8),
        Pattern("vat_sk", r"\bSK\d{10}\b", 0.8),
        Pattern("vat_gb", r"\bGB\d{9}\b", 0.7),
        Pattern("vat_ch", r"\bCHE\d{9}\b", 0.8),
    ]
    recognizers.append(PatternRecognizer(
        supported_entity="EU_VAT", supported_language="en",
        patterns=eu_vat_patterns,
        context=["VAT", "TVA", "Mehrwertsteuer", "MwSt", "IVA", "BTW", "tax number", "VAT number"],
    ))

    # EU Passport
    recognizers.append(PatternRecognizer(
        supported_entity="EU_PASSPORT", supported_language="en",
        patterns=[
            Pattern("eu_passport_2l7d", r"\b[A-Z]{2}\d{7}\b", 0.3),
            Pattern("eu_passport_1l8d", r"\b[A-Z]\d{8}\b", 0.3),
            Pattern("eu_passport_9d",   r"\b\d{9}\b", 0.1),
        ],
        context=["passport", "travel document", "passeport", "Reisepass", "EU passport"],
    ))

    return recognizers
