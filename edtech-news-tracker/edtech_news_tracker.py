#!/usr/bin/env python3
"""
EdTech News Tracker
====================
Daily multilingual news monitoring for Ed-Tech competitors, powered by the
Parallel.ai Search API.

Run from a terminal:
    python edtech_news_tracker.py

See README.md for setup instructions (this is written for a non-developer).
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as dateparser
from tqdm import tqdm

from tracker import checkpoint
from tracker.config import load_settings, Settings, PRESS_WIRE_DOMAINS
from tracker.dedup import deduplicate
from tracker.excel_loader import (
    Company, Geography, TrackingListError, load_tracking_list,
)
from tracker.exporter import RunLog, export
from tracker.parallel_client import ParallelClient, RawResult
from tracker.query_builder import SearchTask, build_tasks_for_company
from tracker.relevance import (
    Article, classify_category, company_mentioned_prominently, detect_geography,
    is_excluded_noise, is_generic_page, score_relevance,
)
from tracker.summarizer import summarize
from tracker.translator import translate_to_english

DATE_FMT = "%Y-%m-%d"
_PRESS_WIRE_DOMAINS_SET = set(PRESS_WIRE_DOMAINS)


# ---------------------------------------------------------------------------
# Date input handling
# ---------------------------------------------------------------------------
def prompt_date_range() -> tuple[datetime, datetime]:
    print("\nEnter the reporting window (format YYYY-MM-DD).")
    print("Press Enter on both to default to the last 24 hours.\n")

    start_raw = input("Start date [Enter = last 24h]: ").strip()
    end_raw = input("End date   [Enter = now]:       ").strip()

    if not start_raw and not end_raw:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(hours=24)
        print(f"Using default window: {start_dt.date()} to {end_dt.date()} (last 24 hours)")
        return start_dt, end_dt

    if not start_raw or not end_raw:
        print("Please provide BOTH a start and end date, or leave BOTH blank for the default.")
        return prompt_date_range()

    try:
        start_dt = datetime.strptime(start_raw, DATE_FMT)
        end_dt = datetime.strptime(end_raw, DATE_FMT)
    except ValueError:
        print(f"Could not parse dates. Use the exact format {DATE_FMT}, e.g. 2026-09-01.")
        return prompt_date_range()

    if start_dt > end_dt:
        print("Start date must be before or equal to the end date. Please try again.")
        return prompt_date_range()

    if end_dt > datetime.now() + timedelta(days=1):
        print("End date is in the future. Please try again.")
        return prompt_date_range()

    return start_dt, end_dt + timedelta(hours=23, minutes=59, seconds=59)


_DATE_SNIFF_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"\d{1,2},?\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?,?\s+\d{4}\b",
    re.IGNORECASE,
)


def _sniff_date(text: str | None) -> datetime | None:
    """Finds an explicit, unambiguous date (e.g. 'May 2, 2023' or
    '2026-10-23') inside free text. Used as a fallback when a result has no
    structured publish-date metadata, and to catch stale content (an old
    article with a dateline baked into the text) that metadata alone missed."""
    if not text:
        return None
    m = _DATE_SNIFF_RE.search(text)
    if not m:
        return None
    try:
        return dateparser.parse(m.group(0), fuzzy=False)
    except (ValueError, OverflowError):
        return None


def _within_window(
    published_raw: str | None, start_dt: datetime, end_dt: datetime, fallback_text: str | None = None
) -> tuple[bool, bool]:
    """Returns (within_window, date_was_determined). Tries the structured
    publish-date field first, then falls back to sniffing an explicit date
    out of `fallback_text` (title/excerpt) -- this catches cases where the
    search result has no date metadata but the text itself has a dateline
    (which, left unhandled, let stale/old articles through as "undated and
    therefore exempt" in earlier runs)."""
    pub_dt = None
    if published_raw:
        try:
            pub_dt = dateparser.parse(published_raw, fuzzy=True)
        except (ValueError, OverflowError):
            pub_dt = None
    if pub_dt is None:
        pub_dt = _sniff_date(fallback_text)
    if pub_dt is None:
        return True, False  # genuinely unknown: keep, but flagged for review by caller
    if pub_dt.tzinfo is not None:
        pub_dt = pub_dt.replace(tzinfo=None)
    return start_dt <= pub_dt <= end_dt, True


# ---------------------------------------------------------------------------
# Per-result processing
# ---------------------------------------------------------------------------
def _raw_result_to_article(
    result: RawResult,
    task: SearchTask,
    geographies: list[Geography],
    settings: Settings,
    start_dt: datetime,
    end_dt: datetime,
) -> Article | None:
    is_official_source = bool(
        result.source_domain
        and (
            (task.company.website and _domain_match(task.company.website, result.source_domain))
            or any(d in result.source_domain for d in _PRESS_WIRE_DOMAINS_SET)
        )
    )

    within_window, date_known = _within_window(
        result.published_date, start_dt, end_dt, fallback_text=f"{result.title} {result.excerpt}"
    )
    if date_known and not within_window:
        return None  # outside the requested reporting window
    if not date_known and not is_official_source:
        # An undated result from a random (non-official, non-wire) source is
        # usually a generic reference page, not a dated news article -- drop
        # it rather than guess. Official/wire pages are kept since the
        # company itself (or the wire) is the authority on it being current.
        return None

    if is_generic_page(result.url, result.title, result.source_domain):
        return None  # LinkedIn/Wikipedia/Crunchbase/"About Us"-style pages, not news

    headline_en, headline_ok = translate_to_english(result.title)
    summary_raw = result.excerpt[:600]
    summary_en, summary_ok = translate_to_english(summary_raw)
    # trim to a 2-3 line summary
    summary_en = summary_en.strip()
    if len(summary_en) > 480:
        summary_en = summary_en[:477] + "..."

    if not company_mentioned_prominently(task.company, headline_en, summary_en):
        return None  # name only appears in passing, not actually about this company

    combined_text = f"{headline_en} {summary_en}"
    category = classify_category(combined_text)
    if category is None:
        return None  # no recognizable news-category signal at all
    if is_excluded_noise(combined_text, category):
        return None

    score = score_relevance(
        task.company, headline_en, summary_en, result.source_domain, within_window, date_known
    )

    review_reasons = []
    if score < settings.relevance_review_threshold:
        review_reasons.append("Low confidence")
    if not date_known:
        review_reasons.append("Date unverified")
    if not headline_ok or not summary_ok:
        review_reasons.append("Translation uncertain")

    review_flag = "; ".join(review_reasons) if review_reasons else "OK"

    geography_name = detect_geography(combined_text, geographies)

    return Article(
        company=task.company.name,
        geography=geography_name,
        category=category,
        headline_en=headline_en or result.title,
        summary_en=summary_en,
        source_name=result.source_domain or "Unknown",
        publication_date=result.published_date,
        url=result.url,
        relevance_score=score,
        review_flag=review_flag,
    )


def _domain_match(website: str, source_domain: str) -> bool:
    w = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    return bool(w) and w in source_domain


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------
def run_company(
    company: Company,
    geographies: list[Geography],
    client: ParallelClient,
    settings: Settings,
    start_dt: datetime,
    end_dt: datetime,
) -> list[Article]:
    tasks = build_tasks_for_company(company, geographies)
    articles: list[Article] = []
    for task in tasks:
        raw_results = client.search(task.objective, task.search_queries, company.name, task.lane)
        for r in raw_results:
            art = _raw_result_to_article(r, task, geographies, settings, start_dt, end_dt)
            if art:
                articles.append(art)
    return articles


def _append_flag(existing: str, note: str) -> str:
    if not existing or existing == "OK":
        return note
    return existing if note in existing else f"{existing}; {note}"


def enrich_with_full_summaries(
    articles: list[Article],
    client: ParallelClient,
    settings: Settings,
    start_dt: datetime,
    end_dt: datetime,
) -> list[Article]:
    """For each (deduplicated) article, fetches the full article text via
    Parallel's extract API, translates it to English if needed, and replaces
    the short search-excerpt summary with a real extractive summary covering
    the article's crux (~400-500 words). Runs only after dedup so each URL
    is fetched once, not once per raw search hit. Falls back to the original
    short summary -- never drops the article -- if extraction fails for a
    URL (paywalled, blocked, etc.).

    Also catches stale content whose dateline only shows up in the full
    body text (not in the search result's metadata or excerpt, so the
    earlier date check couldn't see it) and drops it -- this is what let an
    old "raises Series A" press release through as if it were current in an
    earlier run. Returns the surviving article list."""
    url_to_articles: dict[str, list[Article]] = {}
    for art in articles:
        if art.url:
            url_to_articles.setdefault(art.url, []).append(art)
    urls = list(url_to_articles.keys())
    if not urls:
        return articles

    to_drop: set[int] = set()
    batch_size = 20
    batches = [urls[i : i + batch_size] for i in range(0, len(urls), batch_size)]

    with ThreadPoolExecutor(max_workers=settings.max_concurrent_requests) as pool:
        futures = [pool.submit(client.extract, batch) for batch in batches]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Full-text summaries", unit="batch"):
            content_map = fut.result()
            for url, full_content in content_map.items():
                for art in url_to_articles.get(url, []):
                    if not full_content or not full_content.strip():
                        art.review_flag = _append_flag(art.review_flag, "Full article unavailable - short summary only")
                        continue

                    # Datelines are conventionally near the top of a press
                    # release/article; only sniff the first ~800 chars so an
                    # unrelated date mentioned deep in the body (e.g. "since
                    # its 2016 founding") can't cause a false stale-drop.
                    sniffed = _sniff_date(full_content[:800])
                    if sniffed is not None:
                        if sniffed.tzinfo is not None:
                            sniffed = sniffed.replace(tzinfo=None)
                        if not (start_dt <= sniffed <= end_dt):
                            to_drop.add(id(art))
                            continue

                    translated, translate_ok = translate_to_english(full_content)
                    if not translate_ok:
                        art.review_flag = _append_flag(art.review_flag, "Translation uncertain")
                    art.summary_en = summarize(
                        translated, focus_terms=[art.company], target_words=450, max_words=500
                    )

    if to_drop:
        print(f"  Dropped {len(to_drop)} article(s) that turned out to be older than the reporting window.")
    return [a for a in articles if id(a) not in to_drop]


def main() -> int:
    print("=" * 70)
    print("EdTech News Tracker")
    print("=" * 70)

    settings = load_settings()

    try:
        companies, geographies, validation_messages = load_tracking_list(settings.excel_path)
    except TrackingListError as e:
        print(f"\n[ERROR] {e}")
        return 1

    print(f"\nLoaded {len(companies)} companies and {len(geographies)} geographies "
          f"from '{settings.excel_path.name}'.")
    if validation_messages:
        print("\nValidation notes:")
        for m in validation_messages:
            print(f"  - {m}")
    else:
        print("No validation issues found.")

    start_dt, end_dt = prompt_date_range()
    start_tag, end_tag = start_dt.strftime(DATE_FMT), end_dt.strftime(DATE_FMT)

    completed_companies, articles = checkpoint.load(settings.checkpoint_dir, start_tag, end_tag)
    if completed_companies:
        print(f"\nResuming previous run: {len(completed_companies)} company/companies already completed.")

    remaining = [c for c in companies if c.name not in completed_companies]
    if not remaining:
        print("All companies already completed for this date range.")
    else:
        print(f"\nSearching {len(remaining)} companies across {len(geographies)} geographies...")

    client = ParallelClient(
        api_key=settings.api_key,
        max_concurrent=settings.max_concurrent_requests,
        max_retries=settings.max_retries,
        backoff_base=settings.backoff_base_seconds,
        mode=settings.parallel_mode,
        max_results=settings.max_results_per_query,
    )

    run_start_time = time.time()
    zero_news_companies: list[str] = []

    try:
        with ThreadPoolExecutor(max_workers=settings.max_concurrent_requests) as pool:
            futures = {
                pool.submit(run_company, c, geographies, client, settings, start_dt, end_dt): c
                for c in remaining
            }
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Companies", unit="company"):
                company = futures[fut]
                try:
                    company_articles = fut.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"\n[WARN] Unexpected error processing '{company.name}': {exc}")
                    company_articles = []

                if not company_articles:
                    zero_news_companies.append(company.name)
                articles.extend(company_articles)
                completed_companies.append(company.name)
                checkpoint.save(settings.checkpoint_dir, start_tag, end_tag, completed_companies, articles)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress has been saved -- rerun with the same date range to resume.")
        return 130

    print("\nRetrying any failed queries once more before finalizing...")
    still_failed = client.retry_failed()

    print("Deduplicating articles across sources and languages...")
    deduped = deduplicate(articles)

    print(f"Fetching full article text for {len(deduped)} articles and writing summaries...")
    deduped = enrich_with_full_summaries(deduped, client, settings, start_dt, end_dt)

    run_log = RunLog(
        start_date=start_tag,
        end_date=end_tag,
        companies_searched=[c.name for c in companies],
        geographies_searched=[g.country for g in geographies],
        articles_found=len(deduped),
        companies_with_zero_news=zero_news_companies,
        failed_queries=[f"{fq.company_name} | {fq.lane} | {fq.geography or 'Global'} | {fq.error}" for fq in still_failed],
        duration_seconds=time.time() - run_start_time,
    )

    out_path = export(deduped, run_log, settings.output_dir)
    checkpoint.clear(settings.checkpoint_dir, start_tag, end_tag)

    print("\n" + "=" * 70)
    print(f"Done. {len(deduped)} articles written to: {out_path}")
    print(f"Companies with zero news found: {len(zero_news_companies)}")
    print(f"Failed queries (after retries): {len(still_failed)}")
    print(f"Run duration: {run_log.duration_seconds:.1f}s")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
