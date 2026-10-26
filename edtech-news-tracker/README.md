# EdTech News Tracker

A daily news-monitoring tool that tracks ~280 Ed-Tech competitor companies
across 82 geographies, searching company websites, press-release wires, and
local-language news sources, then produces one Excel report per run.

This guide assumes no prior coding experience. Follow the steps in order.

## 1. One-time setup

### 1.1 Install Python
You need Python 3.10 or newer. If you're not sure whether you have it,
open a terminal in VS Code (`Terminal` menu → `New Terminal`) and run:
```
python3 --version
```
If that fails, install Python from https://www.python.org/downloads/.

### 1.2 Open this folder in VS Code
`File` → `Open Folder...` → select the `edtech-news-tracker` folder.

### 1.3 Install the required packages
In the VS Code terminal, from inside this folder, run:
```
pip install -r requirements.txt
```

### 1.4 Add your Parallel.ai API key
1. Find the file `.env.example` in this folder.
2. Make a copy of it named exactly `.env` (still in this same folder).
3. Open `.env` and replace `your_parallel_api_key_here` with your real
   Parallel.ai API key.
4. Save the file. `.env` is already excluded from version control
   (see `.gitignore`), so your key will never be committed or shared.

   If you skip this step, the script will simply ask you to paste the key
   the first time you run it (the input is hidden as you type).

## 2. Keep your tracking list up to date

Open `edtech_tracking_list.xlsx`. It has two tabs:

- **Companies**: `Company Name`, `Aliases`, `Official Website`, `HQ Country`
  - Add a row to start tracking a new company. Delete a row to stop.
  - Fill in `Aliases` with any past/other brand names, comma-separated
    (e.g. `IDP IELTS, IDP Education`) -- this makes searches far more
    accurate.
  - Filling in `Official Website` and `HQ Country` is optional but strongly
    recommended: it helps the tool tell apart companies that share a common
    name from unrelated businesses. This matters most for short/generic
    names -- real feedback on actual runs showed exactly this: "Apollo",
    "Avant", "ETS" and "Edwin" each pulled in news about an unrelated
    same-named company/product, and all four have a blank `Official
    Website` today. Adding the real domain for a company like that is the
    single highest-impact fix you can make without touching any code.
- **Geographies**: `Country`, `Primary Language(s)`, `Local News Sources`
  - `Primary Language(s)` is pre-filled with a sensible default per country
    -- edit it if a market needs an additional language.
  - `Local News Sources` is optional: add domain names (e.g.
    `timesofindia.com`) to bias the search toward specific local outlets.

Nothing about companies or geographies is hard-coded in the script -- every
run reads this file fresh, so editing it is the only thing you need to do to
change what gets tracked.

> **Note on the starter file included in this project:** it was generated
> from your uploaded `Edtech_Complete_list_of_Competitor__Geography.xlsx`
> (280 companies, 82 countries). That source file listed companies and
> countries as two separate columns, not matched row-by-row, so they have
> been split into their own sheets here. Aliases, websites and HQ country
> were not present in the source and are left blank for your team to fill
> in over time -- the tool works without them, just with lower precision on
> companies that share a name with something else.

## 3. Run the tracker

In the VS Code terminal:
```
python edtech_news_tracker.py
```

You'll be asked for a date range:
```
Start date [Enter = last 24h]: 2026-09-01
End date   [Enter = now]:       2026-09-30
```
Press Enter on both (leave them blank) to default to the last 24 hours --
this is what you'd normally use for the daily run.

A progress bar will show companies being processed. Each company runs 3
focused searches (its own newsroom/press-wire coverage, a broader
local/regional search, and an events/partnerships/awards search added after
reviewing real missed-article feedback); after irrelevant results and
duplicates are removed, there's one more pass that fetches the full text of
each surviving article to build its 400-500 word summary. A full run across
all 280 companies is still expected to be well **under an hour** for a
1-day window (a real test of the earlier 2-search design completed in about
2 minutes, so there's a lot of headroom even with the added 3rd search and
richer settings). Lower `PARALLEL_MODE` to `basic` or `MAX_RESULTS_PER_QUERY`
in `.env` if a run ever gets too slow for your Parallel.ai plan.

### If it gets interrupted
Just run `python edtech_news_tracker.py` again with the **same date range**.
It automatically resumes from the last company it fully finished, instead of
starting over.

## 4. Find your results

Each run produces a file named:
```
output/EdTech_News_<start-date>_to_<end-date>.xlsx
```
It has two tabs:
- **News**: one row per article, with company, geography, category, the
  article title, a ~400-500 word English summary covering the article's
  crux, source name, publication date, and the source link, plus a
  relevance score (0-1) and a review flag. Titles and summaries are
  translated to English automatically when the source article is in another
  language. The tool only keeps results that are genuinely *about* the
  company (not generic profile/directory pages like LinkedIn or Wikipedia,
  and not articles where the name is just mentioned in passing alongside
  others) and that match a real news category. Among those, anything still
  uncertain is kept and flagged (`Low confidence`, `Date unverified`,
  `Full article unavailable - short summary only`, etc.) rather than
  silently dropped, so a human can take a quick look rather than the tool
  guessing wrong.
- **Run Log**: how many companies/geographies were searched, articles
  found, which companies had zero news that day, any queries that failed
  even after retries, and total run time.

## 5. Running it daily
Just repeat step 3 each day, leaving both date fields blank so it defaults
to the last 24 hours. Consider setting a recurring reminder or a scheduled
task (Windows Task Scheduler / macOS `cron`/`launchd`) to run the command
automatically if you want it fully hands-off.

## How it works (for reference)

The code is split into small, single-purpose modules under `tracker/`:
- `config.py` -- settings, API key loading, category list.
- `excel_loader.py` -- reads and validates `edtech_tracking_list.xlsx`.
- `query_builder.py` -- builds 3 focused searches per company: its own
  newsroom/press-wire coverage, a broader local/regional search that lets
  Parallel's multilingual index surface local-language coverage (geography
  is attributed afterward by matching the tracked country names, rather
  than issuing a separate call per country), and an events/partnerships/
  awards search targeting the smaller local stories a generic company-news
  query tends to miss in favor of big funding/M&A headlines.
- `parallel_client.py` -- talks to the Parallel.ai Search and Extract APIs,
  with retry/backoff and a concurrency limit; failed queries are logged and
  retried once more at the end of the run. A failed full-text extraction is
  also retried once on its own (outside a batch), which recovers a
  meaningful share of transient per-URL failures.
- **Dates**: every search objective now states the exact required date
  range explicitly (not just "recent"). An undated result is only kept
  when it's on the company's own verified website (`Official Website` in
  the Excel) -- a press-wire hit with no date is dropped rather than
  assumed current, since real runs showed wire archives (BusinessWire,
  PR Newswire) resurfacing years-old releases with no date metadata often
  enough to be the top complaint. BusinessWire's URLs encode the exact
  publish date in the path itself, which is decoded and checked directly
  wherever present -- the single most reliable date signal available.
- `translator.py` -- translates non-English titles/article text to English.
- `relevance.py` -- drops generic profile/directory pages (LinkedIn,
  Wikipedia, Crunchbase, "About Us" pages) and passing mentions where the
  company isn't actually the subject, scores the rest for relevance,
  disambiguates similarly-named companies, and classifies each surviving
  article into a news category.
- `dedup.py` -- merges duplicate/near-duplicate articles across sources
  (after which each surviving URL's full text is fetched once -- see below
  -- rather than once per raw search hit).
- `summarizer.py` -- after dedup, the full article text is fetched (via
  Parallel's Extract API) and translated if needed, then this picks the
  most representative actual sentences from it (not AI-generated text,
  to avoid misstating facts) to build a ~400-500 word summary capturing
  the article's crux.
- `exporter.py` -- writes the final Excel report.
- `checkpoint.py` -- saves progress so an interrupted run can resume.

`edtech_news_tracker.py` is the single entry point that ties these together.

## Troubleshooting
- **"Tracking list not found"**: make sure `edtech_tracking_list.xlsx` is in
  this same folder and hasn't been renamed.
- **"missing a 'Company Name' column"**: a sheet's header row doesn't match
  the expected column names -- check `edtech_tracking_list.xlsx` against
  section 2 above.
- **Rate limit / repeated failures**: lower `MAX_CONCURRENT_REQUESTS` in
  `.env` (see `.env.example`), or check your Parallel.ai plan's limits.
- **Translation looks off**: `deep-translator` uses a free Google Translate
  backend and occasionally struggles with idioms; these rows are flagged
  `Translation uncertain` in the News sheet for a quick manual check.
