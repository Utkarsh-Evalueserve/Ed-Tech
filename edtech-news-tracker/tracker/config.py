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

    # A real test run of the (then 2-call-per-company) design completed a
    # near-full 280-company list in ~134 seconds -- far under the ~45-60
    # minute target, with plenty of headroom even after adding a 3rd lane
    # (see query_builder) and richer settings below for better recall.
    # Lower this if your Parallel.ai plan's rate limit triggers 429s.
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "4"))
    backoff_base_seconds: float = float(os.getenv("BACKOFF_BASE_SECONDS", "2"))

    relevance_review_threshold: float = float(
        os.getenv("RELEVANCE_REVIEW_THRESHOLD", "0.55")
    )

    # One of: turbo, fast, basic, advanced (increasing thoroughness/latency).
    # Given the time-budget headroom above, "advanced" is now the default
    # for better recall; drop to "basic" if a run ever gets too slow.
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
