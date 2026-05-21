"""
Curriculum: subjects, modules, and concepts.

Each concept has:
  id        : globally unique slug
  title     : human-readable name
  subject   : subject_id
  module    : module_id
  order     : ordering within module
  prereqs   : list of concept ids that should come first (advisory)
"""

# -----------------------------------------------------------------------------
# Subjects + modules
# -----------------------------------------------------------------------------
SUBJECTS = {
    "pnl": {
        "title": "The P&L (Profit & Loss Statement)",
        "aliases": ["pl", "pnl", "income", "incomestatement"],
        "modules": [
            ("pnl_lines", "Module 1.1: P&L Line Items"),
            ("pnl_ratios", "Module 1.2: P&L Ratios & Metrics"),
        ],
    },
    "balance": {
        "title": "The Balance Sheet",
        "aliases": ["balance", "bs", "balancesheet"],
        "modules": [
            ("bs_lines", "Module 2.1: Balance Sheet Line Items"),
            ("bs_ratios", "Module 2.2: Balance Sheet Ratios"),
        ],
    },
    "cashflow": {
        "title": "The Cash Flow Statement",
        "aliases": ["cashflow", "cf", "cfs"],
        "modules": [
            ("cf_lines", "Module 3.1: Cash Flow Line Items"),
            ("cf_ratios", "Module 3.2: Cash Flow Ratios"),
        ],
    },
    "saas": {
        "title": "SaaS & Subscription Metrics",
        "aliases": ["saas", "subscription", "metrics"],
        "modules": [
            ("saas_core", "Module 4.1: SaaS Metrics"),
        ],
    },
    "consulting": {
        "title": "Consulting Frameworks",
        "aliases": ["consulting", "frameworks", "mck", "mckinsey"],
        "modules": [
            ("cons_core", "Module 5.1: Frameworks"),
        ],
    },
    "valuation": {
        "title": "Valuation",
        "aliases": ["valuation", "val", "dcf"],
        "modules": [
            ("val_core", "Module 6.1: Valuation"),
        ],
    },
    "pe": {
        "title": "Private Equity",
        "aliases": ["pe", "privateequity", "lbo"],
        "modules": [
            ("pe_core", "Module 7.1: Private Equity"),
        ],
    },
    "vc": {
        "title": "Venture Capital",
        "aliases": ["vc", "venture"],
        "modules": [
            ("vc_core", "Module 8.1: Venture Capital"),
        ],
    },
}

# -----------------------------------------------------------------------------
# Concepts
# -----------------------------------------------------------------------------
def _c(id_, title, subject, module, order, prereqs=None):
    return {
        "id": id_,
        "title": title,
        "subject": subject,
        "module": module,
        "order": order,
        "prereqs": prereqs or [],
    }


CONCEPTS = []

# --- P&L Line Items ---
_pl = [
    ("revenue", "Revenue / Sales"),
    ("cogs", "Cost of Goods Sold (COGS)"),
    ("gross_profit", "Gross Profit"),
    ("gross_margin", "Gross Margin %"),
    ("opex", "Operating Expenses (OpEx)"),
    ("sga", "SG&A (Selling, General & Administrative)"),
    ("rnd", "R&D Expense"),
    ("depreciation", "Depreciation"),
    ("amortisation", "Amortisation"),
    ("ebit", "Operating Profit / EBIT"),
    ("ebitda", "EBITDA"),
    ("adj_ebitda", "Adjusted EBITDA"),
    ("interest_expense", "Interest Expense"),
    ("tax_expense", "Tax Expense"),
    ("net_income", "Net Income / Net Profit"),
    ("eps", "EPS (Earnings Per Share)"),
    ("read_pnl", "How to Read a Real P&L"),
]
for i, (cid, title) in enumerate(_pl, 1):
    prereqs = [_pl[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "pnl", "pnl_lines", i, prereqs))

# --- P&L Ratios ---
_plr = [
    ("gm_pct", "Gross Margin %"),
    ("om_pct", "Operating Margin %"),
    ("nm_pct", "Net Margin %"),
    ("ebitda_margin", "EBITDA Margin %"),
    ("yoy_growth", "Year-over-Year Growth (YoY)"),
    ("cagr", "CAGR — Compound Annual Growth Rate"),
    ("rev_per_employee", "Revenue per Employee"),
    ("op_leverage", "Operating Leverage"),
]
for i, (cid, title) in enumerate(_plr, 1):
    prereqs = [_plr[i - 2][0]] if i > 1 else ["read_pnl"]
    CONCEPTS.append(_c(cid, title, "pnl", "pnl_ratios", i, prereqs))

# --- Balance Sheet Line Items ---
_bs = [
    ("cash", "Cash & Cash Equivalents"),
    ("ar", "Accounts Receivable"),
    ("inventory", "Inventory"),
    ("prepaid", "Prepaid Expenses"),
    ("current_assets", "Current Assets"),
    ("ppe", "Property, Plant & Equipment (PP&E)"),
    ("goodwill", "Goodwill"),
    ("intangibles", "Intangible Assets"),
    ("noncurrent_assets", "Non-Current / Fixed Assets"),
    ("total_assets", "Total Assets"),
    ("ap", "Accounts Payable"),
    ("st_debt", "Short-term Debt"),
    ("accrued_exp", "Accrued Expenses"),
    ("current_liab", "Current Liabilities"),
    ("lt_debt", "Long-term Debt"),
    ("deferred_rev", "Deferred Revenue"),
    ("noncurrent_liab", "Non-Current Liabilities"),
    ("total_liab", "Total Liabilities"),
    ("share_capital", "Share Capital / Common Stock"),
    ("retained_earnings", "Retained Earnings"),
    ("total_equity", "Total Shareholders' Equity"),
    ("accounting_eq", "The Accounting Equation (A = L + E)"),
    ("read_bs", "How to Read a Real Balance Sheet"),
]
for i, (cid, title) in enumerate(_bs, 1):
    prereqs = [_bs[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "balance", "bs_lines", i, prereqs))

# --- Balance Sheet Ratios ---
_bsr = [
    ("current_ratio", "Current Ratio"),
    ("quick_ratio", "Quick Ratio"),
    ("debt_to_equity", "Debt-to-Equity Ratio"),
    ("net_debt", "Net Debt"),
    ("working_capital", "Working Capital"),
    ("ccc", "Cash Conversion Cycle"),
    ("roa", "Return on Assets (ROA)"),
    ("roe", "Return on Equity (ROE)"),
    ("roic", "Return on Invested Capital (ROIC)"),
    ("book_vs_market", "Book Value vs Market Value"),
]
for i, (cid, title) in enumerate(_bsr, 1):
    prereqs = [_bsr[i - 2][0]] if i > 1 else ["read_bs"]
    CONCEPTS.append(_c(cid, title, "balance", "bs_ratios", i, prereqs))

# --- Cash Flow Line Items ---
_cf = [
    ("cf_why", "Why Cash Flow Exists Separately"),
    ("cfo", "Cash from Operations (CFO)"),
    ("non_cash_addback", "Non-Cash Adjustments (D&A, SBC)"),
    ("wc_changes", "Changes in Working Capital"),
    ("cfi", "Cash from Investing (CFI)"),
    ("capex", "CapEx (Capital Expenditure)"),
    ("cff", "Cash from Financing (CFF)"),
    ("fcf", "Free Cash Flow (FCF)"),
    ("fcff_fcfe", "FCFF vs FCFE"),
    ("read_cfs", "How to Read a Real Cash Flow Statement"),
]
for i, (cid, title) in enumerate(_cf, 1):
    prereqs = [_cf[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "cashflow", "cf_lines", i, prereqs))

# --- Cash Flow Ratios ---
_cfr = [
    ("fcf_yield", "Free Cash Flow Yield"),
    ("cf_to_debt", "Cash Flow to Debt"),
    ("capex_pct_rev", "CapEx as % of Revenue"),
    ("cash_conversion", "Cash Conversion (NI to FCF)"),
]
for i, (cid, title) in enumerate(_cfr, 1):
    prereqs = [_cfr[i - 2][0]] if i > 1 else ["read_cfs"]
    CONCEPTS.append(_c(cid, title, "cashflow", "cf_ratios", i, prereqs))

# --- SaaS Metrics ---
_saas = [
    ("mrr_arr", "MRR / ARR"),
    ("churn", "Churn Rate"),
    ("grr", "Gross Revenue Retention (GRR)"),
    ("nrr", "Net Revenue Retention (NRR)"),
    ("cac", "Customer Acquisition Cost (CAC)"),
    ("ltv", "Lifetime Value (LTV)"),
    ("ltv_cac", "LTV:CAC Ratio"),
    ("arpu", "ARPU"),
    ("payback", "Payback Period"),
    ("rule_of_40", "Rule of 40"),
    ("burn_runway", "Burn Rate and Runway"),
]
for i, (cid, title) in enumerate(_saas, 1):
    prereqs = [_saas[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "saas", "saas_core", i, prereqs))

# --- Consulting Frameworks ---
_cons = [
    ("profitability_split", "The Profitability Split"),
    ("market_entry", "Market Entry Framework"),
    ("ma_assessment", "M&A Assessment"),
    ("pricing_strategy", "Pricing Strategy"),
    ("growth_strategy", "Growth Strategy"),
    ("ops_optimisation", "Operations Optimisation"),
    ("hyp_driven", "Hypothesis-Driven Problem Solving"),
    ("mece", "MECE"),
]
for i, (cid, title) in enumerate(_cons, 1):
    prereqs = [_cons[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "consulting", "cons_core", i, prereqs))

# --- Valuation ---
_val = [
    ("val_why", "Why Valuation Matters"),
    ("ev", "Enterprise Value (EV)"),
    ("equity_value", "Equity Value / Market Cap"),
    ("ev_bridge", "Bridge: EV = Market Cap + Net Debt"),
    ("multiples", "Valuation Multiples (EV/EBITDA, P/E, etc.)"),
    ("cca", "Comparable Company Analysis"),
    ("precedents", "Precedent Transactions"),
    ("dcf", "DCF — Discounted Cash Flow"),
    ("wacc", "WACC — Weighted Average Cost of Capital"),
    ("terminal_value", "Terminal Value (Gordon vs Exit Multiple)"),
    ("sensitivity", "Sensitivity Analysis"),
    ("val_disagree", "When Valuation Methods Disagree"),
]
for i, (cid, title) in enumerate(_val, 1):
    prereqs = [_val[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "valuation", "val_core", i, prereqs))

# --- Private Equity ---
_pe = [
    ("pe_fund", "PE Fund Structure (LP/GP, fees, carry)"),
    ("pe_target", "What Makes a Good PE Target"),
    ("lbo_model", "LBO Model"),
    ("value_creation", "Value Creation Levers"),
    ("dd", "Due Diligence"),
    ("hundred_day_plan", "The 100-Day Plan"),
    ("pe_returns", "PE Return Metrics (IRR, MOIC, TVPI)"),
    ("pe_exits", "PE Exits (IPO / Trade / Secondary)"),
    ("pe_cases", "Real PE Case Studies"),
]
for i, (cid, title) in enumerate(_pe, 1):
    prereqs = [_pe[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "pe", "pe_core", i, prereqs))

# --- Venture Capital ---
_vc = [
    ("vc_fund", "VC Fund Mechanics"),
    ("pre_post_money", "Pre-money / Post-money Valuation"),
    ("dilution", "Dilution"),
    ("cap_table", "Cap Tables"),
    ("term_sheet", "Term Sheets"),
    ("vc_dd", "VC Due Diligence"),
    ("tam_sam_som", "TAM / SAM / SOM"),
    ("vc_portfolio", "VC Portfolio Math"),
    ("vc_cases", "Real VC Case Studies"),
]
for i, (cid, title) in enumerate(_vc, 1):
    prereqs = [_vc[i - 2][0]] if i > 1 else []
    CONCEPTS.append(_c(cid, title, "vc", "vc_core", i, prereqs))


# -----------------------------------------------------------------------------
# Lookup helpers
# -----------------------------------------------------------------------------
CONCEPT_BY_ID = {c["id"]: c for c in CONCEPTS}


def all_concepts():
    return list(CONCEPTS)


def get_concept(cid):
    return CONCEPT_BY_ID.get(cid)


def concepts_in_subject(subject_id):
    return [c for c in CONCEPTS if c["subject"] == subject_id]


def concepts_in_module(module_id):
    return [c for c in CONCEPTS if c["module"] == module_id]


def subject_for(name):
    """Resolve a free-text subject name or alias to subject_id."""
    if not name:
        return None
    n = name.strip().lower().replace(" ", "").replace("&", "")
    for sid, meta in SUBJECTS.items():
        if n == sid or n in meta["aliases"]:
            return sid
    # partial match
    for sid, meta in SUBJECTS.items():
        if n in sid or any(n in a for a in meta["aliases"]):
            return sid
    return None


def find_concept_by_name(query):
    """Loose search of a concept by its title or id."""
    if not query:
        return None
    q = query.strip().lower()
    # exact id match
    if q in CONCEPT_BY_ID:
        return CONCEPT_BY_ID[q]
    # title contains
    for c in CONCEPTS:
        if q == c["title"].lower():
            return c
    for c in CONCEPTS:
        if q in c["title"].lower() or q in c["id"]:
            return c
    return None


def total_concepts():
    return len(CONCEPTS)


def concepts_count_per_subject():
    counts = {}
    for c in CONCEPTS:
        counts[c["subject"]] = counts.get(c["subject"], 0) + 1
    return counts


def concepts_count_per_module():
    counts = {}
    for c in CONCEPTS:
        counts[c["module"]] = counts.get(c["module"], 0) + 1
    return counts


def subject_modules(subject_id):
    return SUBJECTS[subject_id]["modules"]


def subject_title(subject_id):
    return SUBJECTS[subject_id]["title"]
