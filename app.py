"""Wayback Diff -- compare archived versions of any URL from the Wayback Machine.

Enter a URL, browse its Wayback Machine snapshots and their metadata on a
calendar, pick two versions by clicking days, and view the diff between them.

Run with:  shiny run app.py (or: python -m shiny run app.py)
"""

from __future__ import annotations

import calendar
import difflib
import html
from datetime import date
from pathlib import Path

from shiny import App, reactive, render, ui

import wayback

# Styling and client-side behavior live in sibling asset files (styles.css,
# calendar.js) and are inlined into <head> at startup.
_HERE = Path(__file__).parent

# GitHub "mark" logo (octicon), inlined so it needs no external request or
# icon-font dependency. Sized/coloured via the .gh-icon rule in styles.css.
_GITHUB_ICON_SVG = (
    '<svg class="gh-icon" viewBox="0 0 16 16" aria-hidden="true">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38'
    " 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28"
    "-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28"
    "-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02"
    ".08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04"
    " 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75"
    "-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013"
    ' 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path></svg>'
)

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_text(
            "url",
            "URL",
            placeholder="https://example.com",
            width="100%",
        ),
        ui.tooltip(
            ui.input_numeric("limit", "Max snapshots", value=20, min=1, max=3000),
            "Fetches the most recent N captures.",
            placement="right",
        ),
        ui.tooltip(
            ui.input_action_button(
                "fetch", "Look up snapshots", class_="btn-primary", width="100%"
            ),
            "Lists available captures and their metadata. "
            "Page content is downloaded when you compare.",
            placement="right",
        ),
        ui.hr(),
        ui.input_radio_buttons(
            "mode",
            "Compare",
            {"text": "Visible text (strip HTML)", "raw": "Raw source"},
            selected="text",
        ),
        ui.input_radio_buttons(
            "view",
            "Diff view",
            {"side": "Side-by-side", "unified": "Unified"},
            selected="side",
        ),
        ui.tooltip(
            ui.input_switch("persist_cache", "Save pages to disk", value=True),
            "Keeps downloaded pages so they load instantly next time. "
            f"Stored under {wayback.CACHE_DIR}. Turn off "
            "to always fetch fresh and cache nothing.",
            placement="right",
        ),
        ui.panel_conditional(
            "input.persist_cache",
            ui.input_action_button(
                "clear_cache", "Clear saved pages", class_="btn-outline-secondary btn-sm"
            ),
        ),
        ui.tooltip(
            ui.input_action_button(
                "compare", "Compare versions", class_="btn-success", width="100%"
            ),
            "Downloads the two selected captures and shows their differences.",
            placement="right",
        ),
        width=340,
    ),
    ui.head_content(
        ui.include_css(_HERE / "styles.css", method="inline"),
        ui.include_js(_HERE / "calendar.js", method="inline"),
    ),
    ui.div(
        ui.p(
            "Browse a URL's snapshots from the Internet Archive Wayback Machine "
            "on a calendar, pick two captures, and view a diff of "
            "how the page changed.",
            class_="text-secondary mb-1",
        ),
        ui.tags.small(
            ui.a(
                ui.HTML(_GITHUB_ICON_SVG),
                "Source on GitHub",
                href="https://github.com/jrdnbradford/Wayback-Diff",
                target="_blank",
                rel="noopener noreferrer",
            ),
            class_="text-secondary",
        ),
        class_="app-intro mb-3",
    ),
    ui.output_ui("status"),
    ui.navset_card_tab(
        ui.nav_panel(
            "Calendar",
            ui.output_ui("selection_panel"),
            ui.output_ui("calendar"),
        ),
        ui.nav_panel(
            "Diff",
            ui.output_ui("diff_output"),
        ),
        id="main_tabs",
    ),
    title="Wayback Diff",
    fillable=False,
)


# --------------------------------------------------------------------------- #
# Calendar HTML builder
# --------------------------------------------------------------------------- #
_DOW = ["S", "M", "T", "W", "T", "F", "S"]


def render_year_calendar(
    year: int,
    day_map: dict[str, list[int]],
    sel_a_iso: str | None,
    sel_b_iso: str | None,
    first_date: date,
    last_date: date,
) -> ui.Tag:
    """Build a calendar for `year`; days present in `day_map` are clickable
    and carry a capture count. Only months within the snapshot date range
    (`first_date`..`last_date`) are shown."""
    lo_month = first_date.month if year == first_date.year else 1
    hi_month = last_date.month if year == last_date.year else 12
    cal = calendar.Calendar(firstweekday=6)  # weeks start on Sunday
    months = []
    for month in range(lo_month, hi_month + 1):
        cells = [ui.div(d, class_="cal-dow") for d in _DOW]
        for week in cal.monthdatescalendar(year, month):
            for day in week:
                if day.month != month:
                    cells.append(ui.div("", class_="cal-day out"))
                    continue
                iso = day.isoformat()
                hits = day_map.get(iso)
                if not hits:
                    cells.append(ui.div(str(day.day), class_="cal-day empty"))
                    continue
                cls = "cal-day has"
                if iso == sel_a_iso:
                    cls += " sel-a"
                if iso == sel_b_iso:
                    cls += " sel-b"
                count = (
                    ui.span(str(len(hits)), class_="cal-count") if len(hits) > 1 else None
                )
                cells.append(
                    ui.div(
                        str(day.day),
                        count,
                        class_=cls,
                        data_date=iso,
                        title=f"{iso}: {len(hits)} capture(s)",
                    )
                )
        months.append(
            ui.div(
                ui.h6(calendar.month_name[month]),
                ui.div(*cells, class_="cal-grid"),
                class_="cal-month",
            )
        )
    return ui.div(*months, class_="cal-year-grid")


def render_display_note(info: dict, url: str) -> ui.Tag:
    """A summary line + expandable note explaining how this displayed set
    differs from the full Wayback Machine record for `url`. Every capture is
    shown as-is, so the only difference is the most-recent-N fetch limit."""
    summary_line = f"Showing all {info['fetched']} captures fetched (most recent)"
    if info["more_exist"]:
        summary_line += '  ·  older captures exist — raise "Max snapshots"'

    wayback_cal = f"https://web.archive.org/web/*/{url}" if url else "https://web.archive.org"
    return ui.div(
        ui.tags.small(summary_line, class_="text-secondary"),
        ui.tags.details(
            ui.tags.summary(
                "Why might this differ from the Wayback Machine?",
                class_="text-secondary",
            ),
            ui.tags.ul(
                ui.tags.li(
                    f"This app fetches only the most recent {info['limit']} captures "
                    "(set by “Max snapshots”); the Wayback calendar shows every capture."
                ),
                ui.tags.li(
                    ui.a(
                        "Open this URL’s Wayback Machine calendar ↗",
                        href=wayback_cal,
                        target="_blank",
                    )
                ),
            ),
        ),
        class_="display-note",
    )


def next_selection(iso, hits, a, b, a_iso, b_iso):
    """Compute the (Version A, Version B) snapshot indices after a calendar day
    click. Pure function so the selection rules can be unit-tested.

    `iso`   -- clicked day (ISO date string)
    `hits`  -- capture indices for that day, newest-first
    `a`/`b` -- currently selected A/B indices (or None)
    `a_iso`/`b_iso` -- the ISO date of the current A/B (or None)

    A day with multiple captures can fill both slots: clicking it while A is
    already on that day (and B is free) assigns B to a *different* capture of
    the same day. The per-day pickers then fine-tune each slot.
    """
    both_on_day = a is not None and b is not None and iso == a_iso and iso == b_iso
    if both_on_day:
        return None, None  # clear both -> start over
    if a is None:
        return hits[0], b
    if b is None:
        if iso == a_iso:
            other = next((h for h in hits if h != a), None)
            return (a, other) if other is not None else (None, b)  # else deselect A
        return a, hits[0]
    if iso == a_iso:
        return None, b  # deselect A
    if iso == b_iso:
        return a, None  # deselect B
    return hits[0], None  # both filled, new day -> restart from this click


def server(input, output, session):
    snapshots: reactive.Value[list[wayback.Snapshot]] = reactive.Value([])
    error_msg: reactive.Value[str] = reactive.Value("")
    cal_year: reactive.Value[int | None] = reactive.Value(None)
    sel_a: reactive.Value[int | None] = reactive.Value(None)  # snapshot index
    sel_b: reactive.Value[int | None] = reactive.Value(None)
    diff_html: reactive.Value[str] = reactive.Value("")
    # Bumped whenever the content cache changes, so cache badges re-render.
    cache_ver: reactive.Value[int] = reactive.Value(0)
    # Fetch stats + the URL actually queried, for the transparency panel.
    fetch_info: reactive.Value[dict | None] = reactive.Value(None)
    queried_url: reactive.Value[str] = reactive.Value("")

    # ---- Derived: date (iso) -> [snapshot indices], newest-first ---------- #
    @reactive.calc
    def day_map() -> dict[str, list[int]]:
        m: dict[str, list[int]] = {}
        for i, s in enumerate(snapshots.get()):
            dt = s.captured_at
            if dt:
                m.setdefault(dt.date().isoformat(), []).append(i)
        return m

    @reactive.calc
    def years() -> list[int]:
        ys = {s.captured_at.year for s in snapshots.get() if s.captured_at}
        return sorted(ys)

    def _iso_of(idx: int | None) -> str | None:
        if idx is None:
            return None
        snaps = snapshots.get()
        if 0 <= idx < len(snaps) and snaps[idx].captured_at:
            return snaps[idx].captured_at.date().isoformat()
        return None

    # ---- Fetch snapshots -------------------------------------------------- #
    @reactive.effect
    @reactive.event(input.fetch)
    def _load():
        url = input.url().strip()
        error_msg.set("")
        snapshots.set([])
        sel_a.set(None)
        sel_b.set(None)
        diff_html.set("")
        fetch_info.set(None)
        queried_url.set("")
        if not url:
            error_msg.set("Enter a URL.")
            return
        try:
            with ui.Progress(min=0, max=1) as p:
                p.set(0.2, message="Querying the Wayback Machine…")
                listing = wayback.list_snapshots(
                    url,
                    limit=int(input.limit() or 100),
                )
                p.set(1.0)
        except Exception as exc:
            error_msg.set(f"Could not retrieve snapshots: {exc}")
            return
        result = listing.snapshots
        if not result:
            error_msg.set(f"No archived snapshots found for “{url}”.")
        snapshots.set(result)
        queried_url.set(url)
        fetch_info.set(
            {
                "fetched": listing.fetched,
                "limit": listing.limit,
                "more_exist": listing.more_exist,
            }
        )
        yrs = sorted({s.captured_at.year for s in result if s.captured_at})
        cal_year.set(yrs[-1] if yrs else None)

    # ---- Year navigation -------------------------------------------------- #
    @reactive.effect
    @reactive.event(input.cal_prev)
    def _prev_year():
        yrs = years()
        cur = cal_year.get()
        if yrs and cur in yrs:
            i = yrs.index(cur)
            if i > 0:
                cal_year.set(yrs[i - 1])

    @reactive.effect
    @reactive.event(input.cal_next)
    def _next_year():
        yrs = years()
        cur = cal_year.get()
        if yrs and cur in yrs:
            i = yrs.index(cur)
            if i < len(yrs) - 1:
                cal_year.set(yrs[i + 1])

    # ---- Calendar click: assign to A / B ---------------------------------- #
    @reactive.effect
    @reactive.event(input.cal_click)
    def _on_click():
        iso = input.cal_click()
        hits = day_map().get(iso)  # capture indices for that day, newest-first
        if not hits:
            return
        a, b = sel_a.get(), sel_b.get()
        new_a, new_b = next_selection(iso, hits, a, b, _iso_of(a), _iso_of(b))
        sel_a.set(new_a)
        sel_b.set(new_b)

    @reactive.effect
    @reactive.event(input.clear_sel)
    def _clear():
        sel_a.set(None)
        sel_b.set(None)

    @reactive.effect
    @reactive.event(input.clear_cache)
    def _clear_cache():
        n = wayback.clear_disk_cache()
        ui.notification_show(f"Removed {n} saved page(s).")
        cache_ver.set(cache_ver.get() + 1)  # refresh cached/will-fetch badges

    # ---- Refine which capture within a selected day ----------------------- #
    @reactive.effect
    @reactive.event(input.refine_a)
    def _refine_a():
        try:
            sel_a.set(int(input.refine_a()))
        except (TypeError, ValueError):
            pass

    @reactive.effect
    @reactive.event(input.refine_b)
    def _refine_b():
        try:
            sel_b.set(int(input.refine_b()))
        except (TypeError, ValueError):
            pass

    # ---- Status / summary ------------------------------------------------- #
    @render.ui
    def status():
        msg = error_msg.get()
        if msg:
            return ui.div(msg, class_="alert alert-warning", role="alert")
        return None

    # ---- Selection panel (chosen A / B + per-day refine) ------------------ #
    def _slot(letter: str, idx: int | None, refine_id: str) -> ui.Tag:
        snaps = snapshots.get()
        cls = "slot-a" if letter == "A" else "slot-b"
        if idx is None:
            return ui.div(
                ui.span(f"Version {letter}", class_=cls),
                ui.br(),
                ui.help_text("Click a highlighted day."),
            )
        snap = snaps[idx]
        iso = _iso_of(idx)
        same_day = day_map().get(iso, [])
        if wayback.is_cached(snap, use_disk=bool(input.persist_cache())):
            badge = ui.span("cached", class_="badge rounded-pill text-bg-success ms-2")
        else:
            badge = ui.span("will fetch", class_="badge rounded-pill text-bg-secondary ms-2")
        body = [
            ui.span(f"Version {letter}", class_=cls),
            badge,
            ui.br(),
            ui.tags.small(snap.label),
        ]
        if len(same_day) > 1:
            choices = {str(i): (snaps[i].captured_at.strftime("%H:%M:%S UTC")) for i in same_day}
            body.append(
                ui.input_radio_buttons(
                    refine_id,
                    f"{len(same_day)} captures this day:",
                    choices,
                    selected=str(idx),
                )
            )
        return ui.div(*body)

    @render.ui
    def selection_panel():
        cache_ver.get()  # re-render badges when the content cache changes
        input.persist_cache()  # ...or when disk caching is toggled
        if not snapshots.get():
            return None
        return ui.div(
            ui.layout_columns(
                _slot("A", sel_a.get(), "refine_a"),
                _slot("B", sel_b.get(), "refine_b"),
                col_widths=(6, 6),
            ),
            ui.input_action_button(
                "clear_sel", "Clear selection", class_="btn-outline-secondary btn-sm"
            ),
            ui.hr(),
        )

    # ---- Calendar --------------------------------------------------------- #
    @render.ui
    def calendar():
        snaps = snapshots.get()
        if not snaps:
            return ui.help_text("Look up snapshots to see the capture calendar.")
        yr = cal_year.get()
        yrs = years()
        if yr is None:
            return None
        caps = [s.captured_at for s in snaps if s.captured_at]
        first_date, last_date = min(caps).date(), max(caps).date()
        in_year = sum(len(v) for k, v in day_map().items() if k.startswith(str(yr)))
        toolbar = ui.div(
            ui.input_action_button(
                "cal_prev", "<", class_="btn-outline-secondary btn-sm",
                disabled=(not yrs or yr <= yrs[0]),
            ),
            ui.span(str(yr), class_="cal-year"),
            ui.input_action_button(
                "cal_next", "›", class_="btn-outline-secondary btn-sm",
                disabled=(not yrs or yr >= yrs[-1]),
            ),
            ui.tags.small(f"{in_year} capture(s) in {yr}", class_="text-secondary"),
            class_="cal-toolbar",
        )
        info = fetch_info.get()
        panel = render_display_note(info, queried_url.get()) if info else None
        return ui.div(
            toolbar,
            panel,
            render_year_calendar(
                yr,
                day_map(),
                _iso_of(sel_a.get()),
                _iso_of(sel_b.get()),
                first_date,
                last_date,
            ),
        )

    # ---- Compute diff ----------------------------------------------------- #
    @reactive.effect
    @reactive.event(input.compare)
    def _compare():
        # Surface every outcome (diff, "identical" notice, or error) on the
        # Diff tab so the user doesn't have to go looking for it.
        ui.update_navset("main_tabs", selected="Diff")
        snaps = snapshots.get()
        diff_html.set("")
        ia, ib = sel_a.get(), sel_b.get()
        if not snaps:
            diff_html.set("<em>Look up snapshots first.</em>")
            return
        if ia is None or ib is None:
            diff_html.set("<em>Select two versions on the calendar.</em>")
            return
        if ia == ib:
            diff_html.set("<em>Pick two <b>different</b> versions.</em>")
            return
        snap_a, snap_b = snaps[ia], snaps[ib]
        use_disk = bool(input.persist_cache())
        try:
            with ui.Progress(min=0, max=1) as p:
                verb_a = "Loading cached" if wayback.is_cached(snap_a, use_disk=use_disk) else "Fetching"
                p.set(0.2, message=f"{verb_a} version A…")
                content_a = wayback.fetch_content(snap_a, use_disk=use_disk)
                verb_b = "Loading cached" if wayback.is_cached(snap_b, use_disk=use_disk) else "Fetching"
                p.set(0.6, message=f"{verb_b} version B…")
                content_b = wayback.fetch_content(snap_b, use_disk=use_disk)
                p.set(0.9, message="Diffing…")
            # Both versions are now cached; refresh the selection badges.
            cache_ver.set(cache_ver.get() + 1)
        except Exception as exc:
            diff_html.set(
                f"<div class='alert alert-danger'>Could not fetch content: "
                f"{html.escape(str(exc))}</div>"
            )
            return

        if input.mode() == "text":
            content_a = wayback.html_to_text(content_a)
            content_b = wayback.html_to_text(content_b)

        lines_a = content_a.splitlines()
        lines_b = content_b.splitlines()
        # Order chronologically so "from" is older and "to" is newer.
        if snap_a.timestamp > snap_b.timestamp:
            lines_a, lines_b = lines_b, lines_a
            snap_a, snap_b = snap_b, snap_a
        label_a = f"{snap_a.label}"
        label_b = f"{snap_b.label}"

        if input.view() == "side":
            # context=False shows the entire document (not just changed regions).
            table = difflib.HtmlDiff(wrapcolumn=80).make_table(
                lines_a, lines_b, label_a, label_b, context=False
            )
            diff_html.set(f"<div class='diff-wrap'>{table}</div>")
        else:
            diff_html.set(_unified_html(lines_a, lines_b, label_a, label_b))

    @render.ui
    def diff_output():
        content = diff_html.get()
        if not content:
            return ui.help_text(
                "Pick two versions on the calendar, then press “Compare versions”."
            )
        return ui.HTML(content)


def _unified_html(lines_a, lines_b, label_a, label_b) -> str:
    """Colorized unified diff showing the whole document (full context)."""
    # A large context count includes every unchanged line, not just the hunks
    # surrounding changes.
    full_context = max(len(lines_a), len(lines_b), 1)
    diff = difflib.unified_diff(
        lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm="", n=full_context
    )
    out = []
    any_change = False
    for line in diff:
        esc = html.escape(line)
        if line.startswith(("+++", "---", "@@")):
            out.append(f"<span class='u-hdr'>{esc}</span>")
        elif line.startswith("+"):
            out.append(f"<span class='u-add'>{esc}</span>")
            any_change = True
        elif line.startswith("-"):
            out.append(f"<span class='u-sub'>{esc}</span>")
            any_change = True
        else:
            out.append(esc)
    if not any_change:
        return (
            "<div class='alert alert-info'>The two versions are identical after "
            "processing.</div>"
        )
    return f"<pre class='udiff'>{chr(10).join(out)}</pre>"


app = App(app_ui, server)
