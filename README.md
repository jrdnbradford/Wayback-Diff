# Wayback Diff

A [Shiny](https://shiny.posit.co/py/) app that retrieves archived versions of any URL from the **Internet Archive Wayback Machine**, plots the captures on a calendar, and lets you diff two versions side by side.

The main panel has two tabs: **Calendar** (browse and pick versions) and **Diff** (view the comparison).

## What it does

1. **Retrieve** — queries the Wayback Machine [CDX Server API](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server) for the most recent archived snapshots of a URL (no API key needed).
1. **Calendar** — plots captures on a calendar (one year at a time, trimmed to the snapshot date range). Click a day to pick **Version A**, click another for **Version B**. Days with multiple captures show a count badge and expose a per-day picker to choose the exact capture. The selected versions' timestamp, HTTP status, and content type appear in the selection panel above the calendar.
1. **Diff** — compare the two selected versions:
   - **Visible text** (HTML stripped) or **raw source**
   - **Side-by-side** or **unified** diff view (always ordered oldest → newest)

Content is fetched via the Wayback `id_` endpoint, which returns the original archived bytes with no toolbar injection, so the diff reflects real changes.

## How this differs from the Wayback Machine calendar

Every capture is shown as-is — nothing is merged or filtered. The only difference from `web.archive.org/web/*/URL` is the fetch limit:

- **Most recent N only** — only the most recent "Max snapshots" captures are fetched; the Wayback calendar shows every capture. Raise the limit to reach further back. The Calendar tab surfaces this with a summary line and a note.

Because nothing is filtered, the list can include redirect captures (e.g. `301`) and `warc/revisit` records; those have no standalone body, so diffing them may show little or nothing.

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
