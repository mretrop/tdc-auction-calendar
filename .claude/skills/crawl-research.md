---
name: crawl-research
description: Crawl auction vendor sites using Cloudflare Browser Rendering to inspect page structure and data patterns. Saves raw markdown/HTML and summarizes findings inline.
---

# Crawl Research

Crawl auction vendor sites and save raw output for analysis.

## Arguments

- No args or `all`: crawl all sites
- One or more short names (space-separated): crawl only those sites

## Site Registry

| Short Name | URL |
|---|---|
| `realauction` | https://realauction.com/clients |
| `grantstreet` | https://www.grantstreet.com/auctions |
| `bid4assets` | https://www.bid4assets.com/county-tax-sales |
| `cosl` | https://www.cosl.org/ |
| `linebarger` | https://www.lgbs.com/ |
| `sri` | https://www.sriservices.com/ |
| `mvba` | https://mvbalaw.com/tax-sales/ |
| `publicsurplus` | https://www.publicsurplus.com/sms/browse/cataucs?catid=15 |
| `purdue` | https://www.pbfcm.com/taxsale.html |

## Instructions

### Step 1: Validate environment

Check that `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` environment variables are set. Run:

```bash
echo "CF_ACCOUNT=${CLOUDFLARE_ACCOUNT_ID:+set}" && echo "CF_TOKEN=${CLOUDFLARE_API_TOKEN:+set}"
```

If either is not set, tell the user to export them and stop.

### Step 2: Resolve target sites

Parse the skill arguments:
- If no arguments or argument is `all`, target all 9 sites from the registry above.
- Otherwise, match each argument against the short names. If any argument doesn't match, list valid short names and stop.

### Step 3: Crawl sites

Write a temporary Python script to `/tmp/crawl_research.py` and execute it with `uv run python /tmp/crawl_research.py <shortname1> <shortname2> ...`.

The script must:
1. Import `CloudflareFetcher` from `tdc_auction_calendar.collectors.scraping.fetchers.cloudflare`
2. Define the site registry as a dict mapping short names to URLs (same as the table above)
3. Accept site short names as command-line arguments
4. Create `data/research/` directory if it doesn't exist
5. Instantiate `CloudflareFetcher` (it reads env vars automatically)
6. For each target site **sequentially**:
   - Call `await fetcher.fetch(url)` with no `js_code` or `wait_for`
   - On success: save `result.markdown` to `data/research/<shortname>.md` and `result.html` to `data/research/<shortname>.html`. Print `OK <shortname> (<status_code>)`
   - On error: print `FAIL <shortname>: <error>` and continue to next site
7. Call `await fetcher.close()` when done
8. Print a summary line: `Done: X/Y sites crawled successfully`

Here is the exact script to write:

```python
"""Crawl auction vendor sites via Cloudflare Browser Rendering."""
import asyncio
import sys
from pathlib import Path

from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher

SITES = {
    "realauction": "https://realauction.com/clients",
    "grantstreet": "https://www.grantstreet.com/auctions",
    "bid4assets": "https://www.bid4assets.com/county-tax-sales",
    "cosl": "https://www.cosl.org/",
    "linebarger": "https://www.lgbs.com/",
    "sri": "https://www.sriservices.com/",
    "mvba": "https://mvbalaw.com/tax-sales/",
    "publicsurplus": "https://www.publicsurplus.com/sms/browse/cataucs?catid=15",
    "purdue": "https://www.pbfcm.com/taxsale.html",
}

async def main(targets: list[str]) -> None:
    out = Path("data/research")
    out.mkdir(parents=True, exist_ok=True)

    fetcher = CloudflareFetcher()
    ok = 0
    try:
        for name in targets:
            url = SITES[name]
            print(f"Crawling {name} ({url}) ...", flush=True)
            try:
                result = await fetcher.fetch(url)
                if result.markdown:
                    (out / f"{name}.md").write_text(result.markdown)
                if result.html:
                    (out / f"{name}.html").write_text(result.html)
                print(f"  OK {name} ({result.status_code})")
                ok += 1
            except Exception as exc:
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    finally:
        await fetcher.close()

    print(f"\nDone: {ok}/{len(targets)} sites crawled successfully")

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(SITES.keys())
    asyncio.run(main(targets))
```

Run the script with a long timeout (up to 10 minutes for all 9 sites):

```bash
uv run python /tmp/crawl_research.py <args>
```

### Step 4: Read and summarize results

After the script completes, read each saved markdown file from `data/research/`. For each site, provide a summary covering:

- **Page structure:** Is it a list of auctions? A map? Links to sub-pages?
- **Data fields visible:** County, date, sale type, state, vendor, registration deadline, deposit info, etc.
- **Listing format:** Table, cards, links to detail pages, calendar view, etc.
- **Extractability:** Can data be extracted directly from this page, or does it require navigating to sub-pages?
- **Recommended approach:** CSS extraction, LLM extraction, or Cloudflare JSON extraction

### Step 5: Overall recommendations

After summarizing all sites, provide:

- Which sites are the best candidates for new collectors (most structured, data-rich)
- Suggested priority order for building collectors
- Sites requiring special handling (authentication, pagination, heavy JS interaction)
- How the findings should influence the existing collector strategy
