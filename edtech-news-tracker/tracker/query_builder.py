"""
Builds Parallel.ai search requests for a company.

Three query "lanes" per company (down from the original per-geography
design, which issued ~84 calls/company and took ~5 hours for a 280-company
list; real test runs showed the 2-lane version completing in ~2 minutes,
so a 3rd lane was added back in for recall -- see below -- while staying
far under the ~45-60 minute target):
  1. Official/press lane -- the company's own newsroom/press/blog/investor
     pages, plus major press-release wires (PR Newswire, Business Wire,
     GlobeNewswire, Cision, Accesswire). English, global.
  2. Local & regional lane -- one broad, company-specific search that lets
     Parallel's own multilingual web index surface local-language coverage
     from the geographies tracked in the Excel file, instead of issuing a
     separate API call per country. The geography is attributed after the
     fact (see relevance.detect_geography) rather than forced query-by-query.
  3. Events & partnerships lane -- added after reviewing real feedback: most
     of a sample of real missed articles were local event/conference
     appearances, accreditations, awards and small local partnerships --
     content a generic "company + news" query under-indexes for relative to
     big-ticket funding/M&A news. This lane targets that specifically.

This keeps total calls at ~3 per company (vs. ~1 + 82 before), which is what
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


def _date_window_clause(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        return (
            f"The article MUST be published on {start_date}. Do not include older press "
            f"releases or articles, even ones still indexed, cached, or re-shared today -- "
            f"check the actual original publish date, not just whether the page currently "
            f"appears in search results. State the publish date explicitly when you find it."
        )
    return (
        f"The article MUST be published between {start_date} and {end_date} (inclusive). "
        f"Do not include older press releases or articles, even ones still indexed, cached, "
        f"or re-shared within this window -- check the actual original publish date. State "
        f"the publish date explicitly when you find it."
    )


def build_official_press_task(company: Company, start_date: str, end_date: str) -> SearchTask:
    site_hint = f" site:{_domain(company.website)}" if company.website else ""
    wire_sites = " OR ".join(f"site:{d}" for d in PRESS_WIRE_DOMAINS)
    aliases_txt = ", ".join(company.aliases) if company.aliases else "no aliases"

    objective = (
        f"Find news specifically ABOUT the education/ed-tech company '{company.name}' "
        f"(also known as: {aliases_txt}) -- not pages that merely mention the name in passing. "
        f"Primary sources: press releases or news posted on {company.name}'s own newsroom/press/"
        f"blog/investor-relations pages, OR press releases about {company.name} distributed via "
        f"major wire services (PR Newswire, Business Wire, GlobeNewswire, Cision, Accesswire). "
        f"ALSO include an announcement hosted on a PARTNER organization's own newsroom when the "
        f"announcement is specifically about a deal/partnership/program involving {company.name} "
        f"(e.g. the other party in a partnership posting the release on their own site rather than "
        f"{company.name}'s) -- do not require {company.name} to be the one hosting it. "
        f"Topics of interest: {', '.join(CATEGORIES)}. "
        f"Exclude: generic company profile/about/overview pages, directory listings, and routine "
        f"stock price or analyst rating commentary. {_date_window_clause(start_date, end_date)}"
    )
    queries = [
        f"{company.name} newsroom press release{site_hint}",
        f"{_alias_clause(company)} press release ({wire_sites})",
        f"{company.name} announcement OR partnership OR appointment OR award",
        f"{company.name} partners with OR signs agreement with OR collaborates with",
    ]
    return SearchTask(company, "official_press", objective, queries)


def build_local_regional_task(
    company: Company, geographies: List[Geography], start_date: str, end_date: str
) -> SearchTask:
    countries = ", ".join(g.country for g in geographies) if geographies else "any country"
    aliases_txt = ", ".join(company.aliases) if company.aliases else "no aliases"

    objective = (
        f"Find local or regional news coverage, in any local language, that is "
        f"SPECIFICALLY ABOUT the education/ed-tech company '{company.name}' (also known as: "
        f"{aliases_txt}) -- for example a local office opening, a market entry, a partnership "
        f"with a local institution, a regulatory action, or local press coverage of the company. "
        f"Only consider articles where this company is the actual subject of the story, not "
        f"pages that just mention its name alongside many others. Restrict to these tracked "
        f"countries: {countries}. Topics of interest: {', '.join(CATEGORIES)}. "
        f"Exclude: generic company profile/directory pages and routine stock/analyst commentary. "
        f"{_date_window_clause(start_date, end_date)}"
    )
    queries = [
        f'"{company.name}" news',
        f"{_alias_clause(company)} partnership OR funding OR launch OR regulation OR award",
        f"{company.name} local office OR market entry OR local partnership",
        f"{company.name} signs OR appoints OR announces OR organizes",
    ]
    return SearchTask(company, "local_regional", objective, queries)


def build_events_partnerships_task(
    company: Company, geographies: List[Geography], start_date: str, end_date: str
) -> SearchTask:
    countries = ", ".join(g.country for g in geographies) if geographies else "any country"
    aliases_txt = ", ".join(company.aliases) if company.aliases else "no aliases"

    objective = (
        f"Find news about the education/ed-tech company '{company.name}' (also known as: "
        f"{aliases_txt}) attending or hosting a conference/summit/seminar, signing a cooperation "
        f"or accreditation agreement with a school/university/ministry, receiving an industry "
        f"award or analyst recognition, or announcing a smaller local collaboration -- the kind "
        f"of local/regional coverage that a generic company-news search tends to miss in favor of "
        f"big funding/M&A headlines. Restrict to these tracked countries: {countries}. Only count "
        f"articles where {company.name} is the actual subject, not a passing mention. Exclude "
        f"generic company profile/directory pages and routine stock/analyst commentary. "
        f"{_date_window_clause(start_date, end_date)}"
    )
    queries = [
        f"{company.name} conference OR summit OR seminar OR conclave",
        f"{_alias_clause(company)} cooperation agreement OR accreditation OR MOU",
        f"{company.name} award OR recognized OR named",
        f"{company.name} campaign OR scholarship OR exam results OR workshop",
    ]
    return SearchTask(company, "events_partnerships", objective, queries)


def build_tasks_for_company(
    company: Company, geographies: List[Geography], start_date: str, end_date: str
) -> List[SearchTask]:
    return [
        build_official_press_task(company, start_date, end_date),
        build_local_regional_task(company, geographies, start_date, end_date),
        build_events_partnerships_task(company, geographies, start_date, end_date),
    ]
