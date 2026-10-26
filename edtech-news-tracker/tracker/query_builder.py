"""
Builds Parallel.ai search requests for a company.

Two query "lanes" per company (down from the original per-geography design):
  1. Official/press lane -- the company's own newsroom/press/blog/investor
     pages, plus major press-release wires (PR Newswire, Business Wire,
     GlobeNewswire, Cision, Accesswire). English, global.
  2. Local & regional lane -- one broad, company-specific search that lets
     Parallel's own multilingual web index surface local-language coverage
     from the geographies tracked in the Excel file, instead of issuing a
     separate API call per country. The geography is attributed after the
     fact (see relevance.detect_geography) rather than forced query-by-query.

This keeps total calls at ~2 per company (vs. ~1 + 82 before), which is what
actually drives both runtime and false-positive volume down: a handful of
precise, company-specific searches beats dozens of broad ones.

Brand names/aliases are always kept as-is (never translated).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import CATEGORIES, PRESS_WIRE_DOMAINS
from .excel_loader import Company, Geography


@dataclass
class SearchTask:
    company: Company
    lane: str  # "official_press" | "local_regional"
    objective: str
    search_queries: List[str]


def _alias_clause(company: Company) -> str:
    names = company.all_names()
    return " OR ".join(f'"{n}"' for n in names)


def _domain(url: str) -> str:
    if not url:
        return ""
    url = url.replace("https://", "").replace("http://", "").replace("www.", "")
    return url.split("/")[0]


def build_official_press_task(company: Company) -> SearchTask:
    site_hint = f" site:{_domain(company.website)}" if company.website else ""
    wire_sites = " OR ".join(f"site:{d}" for d in PRESS_WIRE_DOMAINS)
    aliases_txt = ", ".join(company.aliases) if company.aliases else "no aliases"

    objective = (
        f"Find recent news specifically ABOUT the education/ed-tech company '{company.name}' "
        f"(also known as: {aliases_txt}) -- not pages that merely mention the name in passing. "
        f"Only count: press releases or news posted on {company.name}'s own newsroom/press/blog/"
        f"investor-relations pages, OR press releases about {company.name} distributed via "
        f"major wire services (PR Newswire, Business Wire, GlobeNewswire, Cision, Accesswire). "
        f"Topics of interest: {', '.join(CATEGORIES)}. "
        f"Exclude: generic company profile/about/overview pages, directory listings, and routine "
        f"stock price or analyst rating commentary."
    )
    queries = [
        f"{company.name} newsroom press release{site_hint}",
        f"{_alias_clause(company)} press release ({wire_sites})",
    ]
    return SearchTask(company, "official_press", objective, queries)


def build_local_regional_task(company: Company, geographies: List[Geography]) -> SearchTask:
    countries = ", ".join(g.country for g in geographies) if geographies else "any country"
    aliases_txt = ", ".join(company.aliases) if company.aliases else "no aliases"

    objective = (
        f"Find recent local or regional news coverage, in any local language, that is "
        f"SPECIFICALLY ABOUT the education/ed-tech company '{company.name}' (also known as: "
        f"{aliases_txt}) -- for example a local office opening, a market entry, a partnership "
        f"with a local institution, a regulatory action, or local press coverage of the company. "
        f"Only consider articles where this company is the actual subject of the story, not "
        f"pages that just mention its name alongside many others. Restrict to these tracked "
        f"countries: {countries}. Topics of interest: {', '.join(CATEGORIES)}. "
        f"Exclude: generic company profile/directory pages and routine stock/analyst commentary."
    )
    queries = [
        f'"{company.name}" news',
        f"{_alias_clause(company)} partnership OR funding OR launch OR regulation OR award",
    ]
    return SearchTask(company, "local_regional", objective, queries)


def build_tasks_for_company(company: Company, geographies: List[Geography]) -> List[SearchTask]:
    return [
        build_official_press_task(company),
        build_local_regional_task(company, geographies),
    ]
