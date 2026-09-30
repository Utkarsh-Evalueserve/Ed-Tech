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

    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "4"))
    backoff_base_seconds: float = float(os.getenv("BACKOFF_BASE_SECONDS", "2"))

    # Per the brief: full coverage by default (missing an article is the main
    # risk). Lower this in .env only if a run needs to be scoped down for
    # cost/time during testing.
    max_geographies_per_company: int = int(
        os.getenv("MAX_GEOGRAPHIES_PER_COMPANY", "0")
    )  # 0 = no limit, search every geography for every company

    relevance_review_threshold: float = float(
        os.getenv("RELEVANCE_REVIEW_THRESHOLD", "0.55")
    )

    # One of: turbo, fast, basic, advanced (increasing thoroughness/cost).
    # Defaults to "advanced" because missing a relevant article is the main
    # risk this tool is meant to avoid; dial down in .env for cost/speed.
    parallel_mode: str = os.getenv("PARALLEL_MODE", "advanced")
    max_results_per_query: int = int(os.getenv("MAX_RESULTS_PER_QUERY", "10"))

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
