"""
Legal / contract domain stoplist.

Terms that NER (GLiNER / SpaCy) frequently misclassifies as PII in legal
and contract documents. Checked case-insensitively during entity filtering.
"""

LEGAL_STOPLIST: frozenset = frozenset({
    # ── Contract parties / roles ──
    "contractor", "subcontractor", "client", "customer", "vendor",
    "supplier", "distributor", "franchisor", "franchisee",
    "licensor", "licensee", "employer", "employee", "consultant",
    "agent", "principal", "assignee", "assignor",
    "guarantor", "beneficiary", "trustee", "grantor", "grantee",
    "lessee", "lessor", "tenant", "landlord", "borrower", "lender",
    "buyer", "seller", "partner", "shareholder", "director",
    "officer", "secretary", "treasurer", "representative",
    "obligor", "obligee", "indemnitor", "indemnitee",
    "party", "parties", "counterparty",
    # ── Job titles / corporate roles (NER → PERSON) ──
    "chairman", "chairwoman", "chairperson", "president",
    "vice president", "manager", "supervisor", "administrator",
    "coordinator", "counsel", "attorney", "auditor", "comptroller",
    "commissioner", "mediator", "arbitrator", "notary",
    "general counsel", "key employee", "key employees",
    "ceo", "cfo", "cto", "coo", "cmo", "cio", "cpo",
    # ── Document / legal structural terms ──
    "order", "agreement", "contract", "amendment", "addendum",
    "exhibit", "schedule", "appendix", "annex", "section",
    "article", "clause", "paragraph", "recital", "preamble",
    "purchase order", "statement of work", "scope of work",
    "whereas", "herein", "thereof", "therein", "hereby",
    "definitions", "interpretation", "counterparts", "announcements",
    "variation", "assignment", "notices", "costs",
    # ── M&A / SPA / corporate transaction terms ──
    "shares", "share", "sale", "completion", "conditions",
    "warranties", "warranty", "representations", "covenants",
    "obligations", "undertakings", "indemnities", "limitations",
    "transaction", "acquisition", "disposal", "transfer",
    "consideration", "purchase price", "closing", "escrow",
    "due diligence", "disclosure", "material adverse",
    "pre-completion", "post-completion", "longstop",
    "lien", "encumbrance", "pledge", "charge", "mortgage",
    "de minimis", "de minimis amount", "basket", "cap",
    "tax", "taxation", "tax covenant", "tax deed",
    "hmrc", "customs", "revenue",
    # ── Legal concepts (capitalized in contracts → NER false positives) ──
    "effective date", "termination date", "commencement date",
    "governing law", "force majeure", "confidential information",
    "intellectual property", "indemnification", "arbitration",
    "term", "territory", "termination", "jurisdiction",
    "liability", "negligence", "damages",
    "breach", "remedy", "waiver", "severability",
    "claim", "claims", "dispute", "proceedings", "litigation",
    "consent", "approval", "authority", "resolution",
    # ── Generic business / corporate terms ──
    "company", "corporation", "entity", "firm", "business",
    "affiliate", "subsidiary", "parent", "division", "branch",
    "enterprise", "venture", "consortium", "syndicate",
    "board", "committee", "department", "office",
    "body corporate", "government", "association", "partnership",
    # ── Generic nouns NER misclassifies as PERSON ──
    "person", "individual", "persons", "individuals",
    "actor", "actors", "creator", "creators", "model", "models",
    "influencer", "influencers", "talent", "talents",
    "candidate", "applicant", "recipient", "subscriber",
    "member", "participant", "attendee", "user", "owner",
    "author", "editor", "contributor", "reviewer", "approver",
    "sender", "receiver", "holder", "bearer", "maker",
    "performer", "speaker", "presenter", "moderator",
    "witness", "signatory", "undersigned",
    "purchase", "invoice", "payment", "delivery", "shipment",
    "name", "practice", "relevant person",
    # ── Short ambiguous words ──
    "will", "may", "case", "show", "set", "lead", "head",
    "share", "note", "record", "draft", "release", "notice",
    # ── Abbreviations ──
    "cta", "nda", "sow", "msa", "sla", "roi", "kpi",
    "llc", "ltd", "inc", "corp", "plc", "gmbh", "sarl", "llp",
    "usd", "eur", "gbp", "jpy", "cny",
    # ── Common software / brand names that are NOT PII ──
    "adobe", "adobe premiere", "adobe premiere pro", "adobe after effects",
    "final cut", "final cut pro", "davinci resolve",
    "photoshop", "illustrator", "figma", "canva",
    "microsoft", "google", "apple", "amazon", "meta",
    # ── Cyrillic homoglyphs ──
    "\u0441lient", "\u0441lient",
})
