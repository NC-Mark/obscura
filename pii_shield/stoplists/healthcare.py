"""
Healthcare / clinical domain stoplist.

Terms that NER misclassifies as PII in clinical notes, medical records,
insurance documents, and healthcare compliance reports.
"""

HEALTHCARE_STOPLIST: frozenset = frozenset({
    # ── Clinical roles ──
    "patient", "provider", "physician", "doctor", "nurse",
    "clinician", "practitioner", "specialist", "surgeon",
    "pharmacist", "therapist", "radiologist", "pathologist",
    "technician", "technologist", "paramedic",
    "attending", "resident", "intern", "fellow",
    "hospitalist", "intensivist", "consultant",
    "primary care", "pcp",
    # ── Facility types ──
    "hospital", "clinic", "practice", "facility",
    "ward", "unit", "department", "floor",
    "icu", "itu", "ccu", "nicu", "picu",
    "emergency department", "ed", "er",
    "operating room", "or", "theatre",
    "outpatient", "inpatient", "ambulatory",
    "long-term care", "skilled nursing", "nursing home",
    "hospice", "palliative",
    # ── Medical specialties (often detected as ORG) ──
    "oncology", "cardiology", "neurology", "radiology",
    "pathology", "psychiatry", "psychology",
    "orthopedics", "orthopaedics",
    "gastroenterology", "endocrinology", "nephrology",
    "pulmonology", "rheumatology", "dermatology",
    "ophthalmology", "otolaryngology", "urology",
    "obstetrics", "gynecology", "pediatrics",
    "geriatrics", "hematology", "immunology",
    "infectious disease", "allergy",
    # ── Procedure / treatment terms ──
    "procedure", "treatment", "therapy", "intervention",
    "surgery", "operation", "biopsy",
    "scan", "imaging", "mri", "ct", "x-ray", "ultrasound",
    "ecg", "ekg", "echo", "eeg",
    "blood test", "lab", "laboratory", "specimen",
    "culture", "culture result", "sensitivity",
    # ── Diagnosis / condition terms ──
    "diagnosis", "condition", "disease", "disorder",
    "syndrome", "injury", "infection", "trauma",
    "chronic", "acute", "subacute",
    "benign", "malignant", "primary", "secondary", "metastatic",
    "stage", "grade", "severity",
    # ── Medication / pharmacy ──
    "medication", "drug", "prescription", "dose",
    "dosage", "regimen", "formulation",
    "tablet", "capsule", "injection", "infusion",
    "topical", "oral", "iv", "im", "sc",
    "prn", "qd", "bid", "tid", "qid",
    "generic", "brand", "formulary",
    "refill", "dispense", "pharmacy",
    # ── Insurance / billing ──
    "payer", "insurer", "plan", "coverage",
    "claim", "benefit", "deductible", "copay", "coinsurance",
    "prior authorization", "referral",
    "icd", "cpt", "drg", "hcpcs",
    "cms", "medicare", "medicaid",
    "hipaa", "phi",
    # ── Administrative ──
    "admission", "discharge", "transfer",
    "encounter", "visit", "appointment",
    "order", "result", "report", "note",
    "progress note", "discharge summary",
    "consent", "advance directive",
    "next of kin", "emergency contact",
})
