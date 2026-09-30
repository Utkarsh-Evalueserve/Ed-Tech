"""
Builds Parallel.ai search requests for a company.

Three query "lanes" per company:
  1. Official site lane   -- newsroom/press/blog/investor pages, English, global.
  2. Press-wire lane      -- PR Newswire/Business Wire/GlobeNewswire/etc, English, global.
  3. Geography lane (xN)  -- local-language search for each tracked geography.

Brand names/aliases are always kept as-is (never translated); only the
category umbrella terms are localized where we have a translation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import CATEGORIES, PRESS_WIRE_DOMAINS
from .excel_loader import Company, Geography

# Category umbrella terms translated into major languages used across the
# tracked geographies. Falls back to English for languages not listed here --
# Parallel's search still matches native-language content against an
# English-language objective/keywords reasonably well, so coverage degrades
# gracefully rather than failing.
CATEGORY_TERMS_BY_LANGUAGE = {
    "english": "funding OR acquisition OR partnership OR leadership change OR layoffs OR lawsuit OR award OR new product launch",
    "french": "financement OR acquisition OR partenariat OR changement de direction OR licenciements OR poursuite judiciaire OR prix OR lancement de produit",
    "spanish": "financiación OR adquisición OR asociación OR cambio de liderazgo OR despidos OR demanda OR premio OR lanzamiento de producto",
    "german": "Finanzierung OR Übernahme OR Partnerschaft OR Führungswechsel OR Entlassungen OR Klage OR Auszeichnung OR Produkteinführung",
    "portuguese": "financiamento OR aquisição OR parceria OR mudança de liderança OR demissões OR processo judicial OR prêmio OR lançamento de produto",
    "arabic": "تمويل OR استحواذ OR شراكة OR تغيير قيادي OR تسريح عمال OR دعوى قضائية OR جائزة OR إطلاق منتج",
    "chinese (mandarin)": "融资 OR 收购 OR 合作伙伴关系 OR 领导层变动 OR 裁员 OR 诉讼 OR 奖项 OR 新产品发布",
    "mandarin chinese": "融资 OR 收购 OR 合作伙伴关系 OR 领导层变动 OR 裁员 OR 诉讼 OR 奖项 OR 新产品发布",
    "chinese (cantonese), english": "融资 OR 收購 OR 合作夥伴關係 OR 領導層變動 OR 裁員 OR 訴訟 OR 獎項 OR 新產品發布",
    "russian": "финансирование OR поглощение OR партнерство OR смена руководства OR увольнения OR судебный иск OR награда OR запуск продукта",
    "italian": "finanziamento OR acquisizione OR partnership OR cambio di leadership OR licenziamenti OR causa legale OR premio OR lancio di prodotto",
    "korean": "투자 유치 OR 인수 OR 파트너십 OR 경영진 교체 OR 정리해고 OR 소송 OR 수상 OR 신제품 출시",
    "japanese": "資金調達 OR 買収 OR 提携 OR 経営陣交代 OR 人員削減 OR 訴訟 OR 受賞 OR 新製品発売",
    "hindi, english": "फंडिंग OR अधिग्रहण OR साझेदारी OR नेतृत्व परिवर्तन OR छंटनी OR मुकदमा OR पुरस्कार OR नया उत्पाद लॉन्च",
    "turkish": "finansman OR satın alma OR ortaklık OR liderlik değişikliği OR işten çıkarma OR dava OR ödül OR ürün lansmanı",
    "indonesian": "pendanaan OR akuisisi OR kemitraan OR pergantian kepemimpinan OR PHK OR gugatan OR penghargaan OR peluncuran produk",
    "vietnamese": "gọi vốn OR mua lại OR hợp tác OR thay đổi lãnh đạo OR sa thải OR kiện tụng OR giải thưởng OR ra mắt sản phẩm",
    "thai": "การระดมทุน OR การเข้าซื้อกิจการ OR ความร่วมมือ OR การเปลี่ยนแปลงผู้บริหาร OR การเลิกจ้าง OR คดีความ OR รางวัล OR เปิดตัวผลิตภัณฑ์",
    "polish": "finansowanie OR przejęcie OR partnerstwo OR zmiana kierownictwa OR zwolnienia OR pozew OR nagroda OR premiera produktu",
    "dutch": "financiering OR overname OR partnerschap OR leiderschapswissel OR ontslagen OR rechtszaak OR prijs OR productlancering",
}


@dataclass
class SearchTask:
    company: Company
    lane: str  # "official" | "press_wire" | "geography"
    geography: Geography | None
    objective: str
    search_queries: List[str]


def _alias_clause(company: Company) -> str:
    names = company.all_names()
    return " OR ".join(f'"{n}"' for n in names)


def build_official_site_task(company: Company) -> SearchTask:
    site_hint = f" site:{_domain(company.website)}" if company.website else ""
    objective = (
        f"Find recent news, press releases, blog posts and investor updates published "
        f"on {company.name}'s own official website (newsroom, press, blog, investor relations "
        f"pages) covering: {', '.join(CATEGORIES)}."
    )
    queries = [
        f"{company.name} newsroom press release{site_hint}",
        f"{company.name} investor relations announcement",
        f"{company.name} official blog update",
    ]
    return SearchTask(company, "official", None, objective, queries)


def build_press_wire_task(company: Company) -> SearchTask:
    wire_sites = " OR ".join(f"site:{d}" for d in PRESS_WIRE_DOMAINS)
    objective = (
        f"Find press releases about {company.name} (also known as: "
        f"{', '.join(company.aliases) if company.aliases else 'no aliases'}) distributed via "
        f"major wire services such as PR Newswire, Business Wire, GlobeNewswire, Cision and "
        f"Accesswire, covering: {', '.join(CATEGORIES)}. Exclude stock price or analyst rating updates."
    )
    queries = [
        f"{_alias_clause(company)} press release ({wire_sites})",
        f"{company.name} funding OR partnership OR acquisition wire",
        f"{company.name} leadership OR layoffs OR lawsuit announcement",
    ]
    return SearchTask(company, "press_wire", None, objective, queries)


def build_geography_task(company: Company, geography: Geography) -> SearchTask:
    lang_key = ",".join(geography.languages).lower() if geography.languages else "english"
    local_terms = CATEGORY_TERMS_BY_LANGUAGE.get(lang_key)
    if local_terms is None:
        # try matching on the first listed language only
        first_lang = (geography.languages[0].lower() if geography.languages else "english")
        local_terms = CATEGORY_TERMS_BY_LANGUAGE.get(first_lang, CATEGORY_TERMS_BY_LANGUAGE["english"])

    source_hint = ""
    if geography.local_sources:
        source_hint = " (" + " OR ".join(f"site:{s}" for s in geography.local_sources) + ")"

    objective = (
        f"Find news articles published in {geography.country}, in the local language(s) "
        f"({', '.join(geography.languages) or 'English'}), about the education/ed-tech company "
        f"{company.name} (also known as: {', '.join(company.aliases) if company.aliases else 'no aliases'}). "
        f"Cover leadership changes, M&A/partnerships/funding, office openings, product launches, "
        f"marketing campaigns, market entry/exit, regulatory news, awards, layoffs, financial "
        f"results and negative news (lawsuits, controversies, data breaches, complaints). "
        f"Do not include routine stock price or analyst rating commentary."
    )
    queries = [
        f'"{company.name}" {geography.country}',
        f"{_alias_clause(company)} {local_terms}{source_hint}",
    ]
    return SearchTask(company, "geography", geography, objective, queries)


def build_tasks_for_company(
    company: Company, geographies: List[Geography], max_geographies: int = 0
) -> List[SearchTask]:
    tasks = [build_official_site_task(company), build_press_wire_task(company)]
    geos = geographies if max_geographies <= 0 else geographies[:max_geographies]
    for geo in geos:
        tasks.append(build_geography_task(company, geo))
    return tasks


def _domain(url: str) -> str:
    if not url:
        return ""
    url = url.replace("https://", "").replace("http://", "").replace("www.", "")
    return url.split("/")[0]
