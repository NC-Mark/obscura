"""
Financial markets domain stoplist.

Terms that NER misclassifies as PII in trading, portfolio management,
client reporting, compliance, and investment banking documents.
"""

FINANCIAL_STOPLIST: frozenset = frozenset({
    # ── Counterparty / relationship roles ──
    "counterparty", "issuer", "obligor", "guarantor",
    "prime broker", "custodian", "depository", "trustee",
    "fund manager", "portfolio manager", "investment manager",
    "advisor", "adviser", "sub-advisor", "sub-adviser",
    "placement agent", "arranger", "underwriter", "dealer",
    "market maker", "liquidity provider", "clearinghouse",
    "central counterparty", "ccp",
    "nominee", "beneficiary owner", "beneficial owner",
    # ── Instrument / asset class names ──
    "bond", "note", "bill", "debenture", "paper",
    "equity", "stock", "share", "warrant", "right",
    "option", "future", "forward", "swap", "swaption",
    "cds", "cdo", "clo", "cmbs", "rmbs", "abs",
    "etf", "etn", "etc", "ucits", "sicav",
    "fund", "trust", "spv", "spac", "reit",
    "certificate", "receipt", "adr", "gdr",
    "commodity", "currency", "fx", "forex",
    "derivative", "structured product", "structured note",
    "convertible", "hybrid", "perpetual",
    # ── Market / trading terms ──
    "market", "exchange", "venue", "platform",
    "index", "benchmark", "reference rate",
    "libor", "sofr", "sonia", "euribor", "estr",
    "spread", "yield", "coupon", "dividend",
    "maturity", "tenor", "duration", "convexity",
    "principal", "notional", "face value", "par",
    "premium", "discount", "accrued", "clean", "dirty",
    "bid", "ask", "offer", "mid", "last",
    "volume", "open interest", "turnover",
    "settlement", "clearing", "delivery",
    "margin", "collateral", "haircut", "variation margin",
    "initial margin", "maintenance margin",
    "netting", "novation", "compression",
    # ── Risk / analytics terms ──
    "delta", "gamma", "vega", "theta", "rho",
    "duration", "modified duration", "dv01", "pv01",
    "var", "cvar", "es", "expected shortfall",
    "stress", "scenario", "sensitivity",
    "alpha", "beta", "sharpe", "sortino", "treynor",
    "correlation", "volatility", "sigma",
    "drawdown", "tracking error", "information ratio",
    # ── Portfolio / fund terms ──
    "portfolio", "allocation", "weighting", "exposure",
    "nav", "aum", "auc",
    "return", "performance", "benchmark",
    "long", "short", "net", "gross",
    "leverage", "hedged", "unhedged",
    "rebalance", "rebalancing", "drift",
    # ── Regulatory / compliance terms ──
    "kyc", "aml", "cft", "fatca", "crs",
    "mifid", "emir", "dodd-frank", "basel",
    "suitability", "appropriateness",
    "reportable", "reporting obligation",
    "regulatory capital", "risk-weighted asset", "rwa",
    "lcr", "nsfr", "leverage ratio",
    "sar", "str", "suspicious transaction",
    "beneficial ownership", "ubo",
    # ── Trade lifecycle ──
    "trade", "transaction", "execution", "confirmation",
    "allocation", "affirmation", "matching",
    "settlement date", "value date", "trade date",
    "t+1", "t+2", "t+3",
    "fail", "buy-in", "close-out",
    # ── Desk / division names ──
    "rates", "credit", "equities", "fx", "commodities",
    "prime services", "prime brokerage",
    "sales", "trading", "structuring", "origination",
    "research", "quant", "risk management",
    "operations", "middle office", "back office",
    "compliance", "legal", "finance",
    # ── Common financial abbreviations ──
    "p&l", "pnl", "mtm", "mark-to-market",
    "ipo", "m&a", "lbo", "mbo", "vc", "pe",
    "spv", "spe", "holding company",
    "waci", "esg", "sri",
})
