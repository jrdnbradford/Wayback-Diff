# Wayback Diff

[![Tests](https://img.shields.io/github/actions/workflow/status/jrdnbradford/Wayback-Diff/tests.yml?branch=main&label=Tests&logo=github&logoColor=white)](https://github.com/jrdnbradford/Wayback-Diff/actions/workflows/tests.yml)
[![Built with Shiny](https://img.shields.io/badge/Built%20with-Shiny-447099?logo=posit&logoColor=white)](https://shiny.posit.co/py/)
[![Live on Connect Cloud](https://img.shields.io/badge/Live%20on-Connect%20Cloud-4c4cff?logo=posit&logoColor=white)](https://019f3957-cd1e-0735-4665-d5fb21274822.share.connect.posit.cloud)

A [Shiny](https://shiny.posit.co/py/) app that retrieves archived versions of any URL from the **Internet Archive Wayback Machine**, plots the captures on a calendar, and lets you diff two versions side by side.

The main panel has two tabs: **Calendar** (browse and pick versions) and **Diff** (view the comparison).

## What it does

1. **Retrieve** — queries the Wayback Machine [CDX Server API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server) for the most recent archived snapshots of a URL (no API key needed).

1. **Calendar** — plots captures on a calendar (one year at a time, trimmed to the snapshot date range) for comparison.

1. **Diff** — compare the two selected versions:
   - **Visible text** (HTML stripped) or **raw source**
   - **Side-by-side** or **unified** diff view

Content is fetched via the Wayback `id_` endpoint, which returns the original archived bytes with no toolbar injection, so the diff reflects real changes.

## How this differs from the Wayback Machine calendar

- **Most recent N only** — only the most recent "Max snapshots" captures are fetched; the Wayback calendar shows every capture. Raise the limit to reach further back.

The list can include redirect captures (e.g. `301`) and `warc/revisit` records; those have no standalone body, so diffing them may show little or nothing.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
shiny run app.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## License

[MIT](LICENSE)
