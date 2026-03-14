# GitHub Actions Cron Workflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate auction data collection and Supabase sync via GitHub Actions cron jobs.

**Architecture:** Four separate workflow files, one per collector tier, each with its own cron schedule. Each workflow follows the same pattern: checkout → install uv → install deps → collect → sync. Separate files avoid the GitHub Actions limitation where multiple `schedule` entries all trigger the same workflow with no way to distinguish which cron fired.

**Tech Stack:** GitHub Actions, uv, existing CLI commands

---

## File Structure

| File | Purpose |
|------|---------|
| `.github/workflows/collect-statutory.yml` | Weekly statutory collection |
| `.github/workflows/collect-state-agencies.yml` | Daily state agency collection |
| `.github/workflows/collect-public-notices.yml` | Twice-daily public notice collection |
| `.github/workflows/collect-county-websites.yml` | Daily county website collection |

**Why four files instead of one?** GitHub Actions triggers _all_ jobs in a workflow for each `schedule` entry. With four cron entries in one workflow, the public-notices cron (every 12h) would trigger all four jobs every 12 hours — requiring each job to check the current time to decide whether to run. Separate files are simpler, more readable, and each job runs exactly when its cron fires.

---

## Chunk 1: Statutory Workflow (weekly)

### Task 1: Create the statutory collection workflow

**Files:**
- Create: `.github/workflows/collect-statutory.yml`

- [ ] **Step 1: Create `.github/workflows/` directory**

Run: `mkdir -p .github/workflows`

- [ ] **Step 2: Write the workflow file**

Create `.github/workflows/collect-statutory.yml`:

```yaml
name: "Collect: Statutory (weekly)"

on:
  schedule:
    - cron: "0 3 * * 0"  # Sunday 3am UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: collect-statutory
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v4
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Collect statutory auction data
        run: uv run tdc-auction-calendar collect --collectors statutory

      - name: Sync to Supabase
        run: uv run tdc-auction-calendar sync supabase
```

- [ ] **Step 3: Validate YAML syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/collect-statutory.yml'))"`
Expected: no errors (exit 0)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/collect-statutory.yml
git commit -m "ci: add statutory collection workflow (issue #23)"
```

---

## Chunk 2: State Agencies Workflow (daily)

### Task 2: Create the state agencies collection workflow

**Files:**
- Create: `.github/workflows/collect-state-agencies.yml`

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/collect-state-agencies.yml`:

```yaml
name: "Collect: State Agencies (daily)"

on:
  schedule:
    - cron: "0 4 * * *"  # Daily 4am UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: collect-state-agencies
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v4
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Collect state agency auction data
        run: >-
          uv run tdc-auction-calendar collect
          --collectors arkansas_state_agency
          --collectors california_state_agency
          --collectors colorado_state_agency
          --collectors iowa_state_agency

      - name: Sync to Supabase
        run: uv run tdc-auction-calendar sync supabase
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/collect-state-agencies.yml'))"`
Expected: no errors (exit 0)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/collect-state-agencies.yml
git commit -m "ci: add state agencies collection workflow (issue #23)"
```

---

## Chunk 3: Public Notices Workflow (twice daily)

### Task 3: Create the public notices collection workflow

**Files:**
- Create: `.github/workflows/collect-public-notices.yml`

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/collect-public-notices.yml`:

```yaml
name: "Collect: Public Notices (twice daily)"

on:
  schedule:
    - cron: "0 6,18 * * *"  # 6am and 6pm UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: collect-public-notices
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v4
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Collect public notice auction data
        run: >-
          uv run tdc-auction-calendar collect
          --collectors florida_public_notice
          --collectors minnesota_public_notice
          --collectors new_jersey_public_notice
          --collectors north_carolina_public_notice
          --collectors pennsylvania_public_notice
          --collectors south_carolina_public_notice
          --collectors utah_public_notice

      - name: Sync to Supabase
        run: uv run tdc-auction-calendar sync supabase
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/collect-public-notices.yml'))"`
Expected: no errors (exit 0)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/collect-public-notices.yml
git commit -m "ci: add public notices collection workflow (issue #23)"
```

---

## Chunk 4: County Websites Workflow (daily)

### Task 4: Create the county websites collection workflow

**Files:**
- Create: `.github/workflows/collect-county-websites.yml`

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/collect-county-websites.yml`:

```yaml
name: "Collect: County Websites (daily)"

on:
  schedule:
    - cron: "0 5 * * *"  # Daily 5am UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: collect-county-websites
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v4
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Collect county website auction data
        run: uv run tdc-auction-calendar collect --collectors county_website

      - name: Sync to Supabase
        run: uv run tdc-auction-calendar sync supabase
```

- [ ] **Step 2: Validate YAML syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/collect-county-websites.yml'))"`
Expected: no errors (exit 0)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/collect-county-websites.yml
git commit -m "ci: add county websites collection workflow (issue #23)"
```

---

## Chunk 5: Verify & Push

### Task 5: Final validation and push

- [ ] **Step 1: Validate all workflow files**

Run: `for f in .github/workflows/collect-*.yml; do echo "--- $f ---"; uv run python -c "import yaml; yaml.safe_load(open('$f')); print('OK')"; done`
Expected: all four files print "OK"

- [ ] **Step 2: Verify `workflow_dispatch` works locally**

Run: `grep -l workflow_dispatch .github/workflows/collect-*.yml | wc -l`
Expected: `4` (all four workflows support manual trigger)

- [ ] **Step 3: Verify concurrency groups are unique**

Run: `grep 'group:' .github/workflows/collect-*.yml`
Expected: four different concurrency groups (`collect-statutory`, `collect-state-agencies`, `collect-public-notices`, `collect-county-websites`)

- [ ] **Step 4: Push and verify workflows appear on GitHub**

Run: `git push`
Then check: `gh workflow list`
Expected: four new workflows listed

- [ ] **Step 5: Test manual dispatch of statutory workflow**

Run: `gh workflow run "Collect: Statutory (weekly)"`
Then check: `gh run list --workflow="Collect: Statutory (weekly)" --limit 1`
Expected: run appears in list (may be queued or in_progress)
