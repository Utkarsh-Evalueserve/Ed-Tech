"""
Config loader: environment variables, API key handling, and tunable constants.

All secrets come from .env (via python-dotenv) or a secure runtime prompt.
Nothing here is hard-coded business data -- companies/geographies live in Excel.
"""
from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# News categories (must match the brief exactly; used for classification)
# ---------------------------------------------------------------------------
CATEGORIES = [
    "Executive & Leadership Changes",
    "Strategic Moves (M&A, Partnerships, Investments, Funding)",
    "Office Openings/Expansions",
    "New Products/Launches",
    "Marketing Campaigns",
    "Market Entry/Exit",
    "Government/Regulatory Developments",
    "Awards",
    "Layoffs & Restructuring",
    "Financial Results",
    "Negative News (Lawsuits, Controversies, Data Breaches, Regulatory Action, Complaints)",
]

# Content to actively exclude even if it mentions a tracked company.
EXCLUDE_PATTERNS = [
    r"\bshare(s)?\s+(price|rose|fell|gained|dropped|closed)\b",
    r"\bstock\s+(price|movement|split|buyback)\b",
    r"\banalyst\s+(rating|upgrade|downgrade|price target)\b",
    r"\bmarket\s+commentary\b",
    r"\btrading\s+(volume|session|update)\b",
]

PRESS_WIRE_DOMAINS = [
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
    "cision.com",
    "accesswire.com",
    "einpresswire.com",
]

# ---------------------------------------------------------------------------
# Runtime-tunable settings (env-overridable, sensible defaults)
# ---------------------------------------------------------------------------


@dataclass
class Settings:
    api_key: str
    excel_path: Path = PROJECT_ROOT / "edtech_tracking_list.xlsx"
    output_dir: Path = PROJECT_ROOT / "output"
    checkpoint_dir: Path = PROJECT_ROOT / ".state"

    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "15"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "4"))
    backoff_base_seconds: float = float(os.getenv("BACKOFF_BASE_SECONDS", "2"))

    relevance_review_threshold: float = float(
        os.getenv("RELEVANCE_REVIEW_THRESHOLD", "0.55")
    )

    # A full 82-geography sweep for every company proved expensive (~$500
    # for one run) because the large majority of (company, geography) pairs
    # find nothing -- most companies only ever generate news in a handful
    # of countries, if any, on a given day. Rather than searching all 82
    # countries for every company regardless of relevance, the per-geography
    # sweep now only runs for companies in these Category Code tiers (from
    # the tracking list's Category Code column); every other company still
    # gets the 2 cheap official/global searches, just not the 82-country
    # sweep. Default: A (English/Language Learning), B (Assessment/Exam),
    # C (EdTech/Online Learning/Publishing) -- the categories where local,
    # country-specific news (local partnerships, exam centers, regional
    # launches) is most central to the business and most likely to be
    # missed by a global-only search. A company with no Category Code set
    # (not in the master list) defaults to getting the full sweep anyway,
    # so an untagged company's coverage is never silently reduced.
    full_sweep_category_codes: set[str] = field(
        default_factory=lambda: {
            c.strip().upper() for c in os.getenv("FULL_SWEEP_CATEGORIES", "A,B,C").split(",") if c.strip()
        }
    )

    # One of: turbo, fast, basic, advanced (increasing thoroughness/latency,
    # and -- as far as can be observed without published per-mode pricing --
    # cost). "basic" is a reasonable default for the official/global lanes,
    # which are comparatively few calls (560 total) with a good hit rate.
    parallel_mode: str = os.getenv("PARALLEL_MODE", "basic")
    max_results_per_query: int = int(os.getenv("MAX_RESULTS_PER_QUERY", "10"))
    # The geography lane is the expensive one (tens of thousands of calls,
    # most finding nothing) -- a low max_results here costs nothing in
    # practice (there's rarely more than 1-2 genuine local hits per country
    # per day even for an active company) while keeping each call cheaper.
    geography_max_results_per_query: int = int(os.getenv("GEOGRAPHY_MAX_RESULTS_PER_QUERY", "3"))

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("PARALLEL_API_KEY", "").strip()
    if not api_key:
        print("\nPARALLEL_API_KEY not found in environment or .env file.")
        api_key = getpass.getpass("Enter your Parallel.ai API key (input hidden): ").strip()
        if not api_key:
            raise SystemExit("No API key provided. Exiting.")

    return Settings(api_key=api_key)
