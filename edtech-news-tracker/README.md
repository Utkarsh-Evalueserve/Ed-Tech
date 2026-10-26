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
    name from unrelated businesses.
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

A progress bar will show companies being processed. Each company runs 2
focused searches (its own newsroom/press-wire coverage, and a broader
local/regional search), so a full run across all 280 companies is typically
**under an hour** for a 1-day window (around 560 API calls total). Raise
`MAX_CONCURRENT_REQUESTS` in `.env` if you want it faster and your Parallel.ai
plan's rate limit allows it; switch `PARALLEL_MODE` to `advanced` if you'd
rather trade some speed for deeper recall.

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
- **News**: one row per article, with company, geography, category, an
  English headline and 2-3 line summary, source, publication date, URL, a
  relevance score (0-1), and a review flag. The tool only keeps results that
  are genuinely *about* the company (not generic profile/directory pages like
  LinkedIn or Wikipedia, and not articles where the name is just mentioned
  in passing alongside others) and that match a real news category. Among
  those, anything still uncertain is kept and flagged (`Low confidence`,
  `Date unverified`, etc.) rather than silently dropped, so a human can take
  a quick look rather than the tool guessing wrong.
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
- `query_builder.py` -- builds 2 focused searches per company: one for its
  own newsroom/press-wire coverage, and one broader local/regional search
  that lets Parallel's multilingual index surface local-language coverage
  (geography is attributed afterward by matching the tracked country names,
  rather than issuing a separate call per country).
- `parallel_client.py` -- talks to the Parallel.ai Search API, with retry/
  backoff and a concurrency limit; failed queries are logged and retried
  once more at the end of the run.
- `translator.py` -- translates non-English headlines/summaries to English.
- `relevance.py` -- drops generic profile/directory pages (LinkedIn,
  Wikipedia, Crunchbase, "About Us" pages) and passing mentions where the
  company isn't actually the subject, scores the rest for relevance,
  disambiguates similarly-named companies, and classifies each surviving
  article into a news category.
- `dedup.py` -- merges duplicate/near-duplicate articles across sources.
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
