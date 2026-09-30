"""
Relevance filtering, disambiguation, category classification and scoring.

Nothing is ever silently dropped for being low-confidence: items below the
review threshold are kept and flagged for manual review instead. Only items
that are pure stock/analyst noise (the brief's explicit exclude list) with no
other topical signal are filtered out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .config import CATEGORIES, EXCLUDE_PATTERNS, PRESS_WIRE_DOMAINS
from .excel_loader import Company

_EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)

_CATEGORY_KEYWORDS = {
    "Executive & Leadership Changes": ["ceo", "cfo", "coo", "appoint", "steps down", "resign", "named president", "new chief", "hires", "promoted"],
    "Strategic Moves (M&A, Partnerships, Investments, Funding)": ["acquisition", "acquire", "merger", "partnership", "invest", "funding", "raises", "series a", "series b", "series c", "stake"],
    "Office Openings/Expansions": ["opens office", "expansion", "new office", "expands to", "opens new"],
    "New Products/Launches": ["launch", "unveils", "introduces", "new product", "rolls out", "release of"],
    "Marketing Campaigns": ["campaign", "marketing", "brand partnership", "sponsorship"],
    "Market Entry/Exit": ["enters market", "market entry", "exits", "withdraws from", "shuts down operations"],
    "Government/Regulatory Developments": ["regulation", "regulatory", "government", "ministry", "policy", "compliance", "approval from"],
    "Awards": ["award", "wins", "recognized", "honored", "named best"],
    "Layoffs & Restructuring": ["layoff", "layoffs", "restructuring", "job cuts", "workforce reduction"],
    "Financial Results": ["quarterly results", "annual report", "revenue", "earnings", "financial results"],
    "Negative News (Lawsuits, Controversies, Data Breaches, Regulatory Action, Complaints)": ["lawsuit", "sues", "data breach", "controversy", "complaint", "fined", "investigation", "scandal"],
}

_INDUSTRY_CONTEXT = [
    "education", "edtech", "ed-tech", "learning", "school", "university",
    "student", "curriculum", "e-learning", "online course", "test prep",
    "language learning", "assessment", "training",
]


@dataclass
class Article:
    company: str
    geography: str
    category: str
    headline_en: str
    summary_en: str
    source_name: str
    publication_date: Optional[str]
    url: str
    relevance_score: float
    review_flag: str
    other_source_urls: List[str] = field(default_factory=list)
    _dedup_key: str = ""


def is_excluded_noise(text: str, matched_category: Optional[str]) -> bool:
    """True only when the ONLY signal is stock/analyst noise and no other
    category keyword matched -- never used to drop a genuinely relevant story."""
    if matched_category is not None:
        return False
    return bool(_EXCLUDE_RE.search(text))


def classify_category(text: str) -> Optional[str]:
    lower = text.lower()
    best_cat, best_hits = None, 0
    for cat in CATEGORIES:
        hits = sum(1 for kw in _CATEGORY_KEYWORDS[cat] if kw in lower)
        if hits > best_hits:
            best_cat, best_hits = cat, hits
    return best_cat


def score_relevance(
    company: Company,
    headline: str,
    excerpt: str,
    source_domain: str,
    within_date_window: bool,
) -> float:
    text = f"{headline} {excerpt}".lower()
    score = 0.0

    # Exact company/alias name match
    if any(name.lower() in text for name in company.all_names()):
        score += 0.35

    # Official domain match is the strongest disambiguation signal
    if company.website and _domain(company.website) and _domain(company.website) in source_domain:
        score += 0.3

    # Known press-wire source is a reasonably strong signal
    if any(d in source_domain for d in PRESS_WIRE_DOMAINS):
        score += 0.15

    # Industry context words help disambiguate generic company names
    if any(term in text for term in _INDUSTRY_CONTEXT):
        score += 0.2

    if within_date_window:
        score += 0.1
    else:
        score -= 0.2

    return max(0.0, min(1.0, round(score, 2)))


def _domain(url: str) -> str:
    if not url:
        return ""
    url = url.replace("https://", "").replace("http://", "").replace("www.", "")
    return url.split("/")[0]
