"""Tests for the presentation helpers in app.py (pure functions that return
HTML fragments)."""

import re
from datetime import date

import app


# --------------------------------------------------------------------------- #
# render_year_calendar
# --------------------------------------------------------------------------- #
def _months(html: str) -> list[str]:
    return re.findall(r"<h6>([A-Za-z]+)</h6>", html)


def test_calendar_clamps_to_snapshot_month_range():
    # Captures only in Feb and Nov 2015: show Feb..Nov, drop Jan and Dec.
    day_map = {"2015-02-10": [0], "2015-11-20": [1]}
    html = str(
        app.render_year_calendar(2015, day_map, None, None, date(2015, 2, 10), date(2015, 11, 20))
    )
    assert _months(html) == [
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
    ]


def test_calendar_keeps_empty_in_between_months():
    # A gap month (with no captures) inside the range is still rendered.
    day_map = {"2015-02-10": [0], "2015-11-20": [1]}
    html = str(
        app.render_year_calendar(2015, day_map, None, None, date(2015, 2, 10), date(2015, 11, 20))
    )
    assert "June" in _months(html)  # no captures in June, still shown


def test_calendar_first_year_of_multiyear_range():
    day_map = {"2010-06-03": [0]}
    html = str(
        app.render_year_calendar(2010, day_map, None, None, date(2010, 6, 3), date(2012, 3, 1))
    )
    # 2010 is the first year -> June..December (no Jan..May).
    assert _months(html) == [
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]


def test_calendar_selection_classes_and_count_badge():
    day_map = {"2020-01-05": [0], "2020-01-06": [1, 2]}
    html = str(
        app.render_year_calendar(2020, day_map, "2020-01-05", "2020-01-06", date(2020, 1, 5), date(2020, 1, 6))
    )
    assert "sel-a" in html
    assert "sel-b" in html
    assert 'data-date="2020-01-05"' in html
    assert "cal-count" in html  # the day with two captures shows a count badge


# --------------------------------------------------------------------------- #
# render_display_note
# --------------------------------------------------------------------------- #
def test_transparency_summary_and_wayback_link():
    html = str(
        app.render_display_note({"fetched": 12, "limit": 100, "more_exist": False}, "https://example.com")
    )
    assert "Showing all 12 captures fetched (most recent)" in html
    assert "older captures exist" not in html
    assert "web.archive.org/web/*/https://example.com" in html


def test_transparency_more_exist_hint():
    html = str(app.render_display_note({"fetched": 5, "limit": 5, "more_exist": True}, "x"))
    assert "older captures exist" in html


# --------------------------------------------------------------------------- #
# _unified_html
# --------------------------------------------------------------------------- #
def test_unified_html_shows_full_document():
    a = [f"line {i}" for i in range(10)]
    b = list(a)
    b[5] = "line 5 CHANGED"
    html = app._unified_html(a, b, "A", "B")
    # Unchanged lines far from the change are still present (full context).
    assert "line 0" in html
    assert "line 8" in html
    assert "CHANGED" in html
    assert "u-add" in html and "u-sub" in html


def test_unified_html_identical_message():
    a = ["same", "content"]
    html = app._unified_html(a, list(a), "A", "B")
    assert "identical" in html.lower()


# --------------------------------------------------------------------------- #
# next_selection (calendar A/B selection rules)
# --------------------------------------------------------------------------- #
def test_selection_first_click_sets_a():
    assert app.next_selection("2020-01-01", [0], None, None, None, None) == (0, None)


def test_selection_second_different_day_sets_b():
    # A already on day 1 (index 0); click day 2 (index 5) -> B.
    assert app.next_selection("2020-01-02", [5], 0, None, "2020-01-01", None) == (0, 5)


def test_selection_same_day_multi_capture_fills_b_with_different_capture():
    # Day has two captures [0, 1], A is the latest (0). Clicking the same day
    # again puts B on the *other* capture (1) -> A and B from the same day.
    assert app.next_selection("2020-01-01", [0, 1], 0, None, "2020-01-01", None) == (0, 1)


def test_selection_same_day_single_capture_deselects_a():
    # Single-capture day clicked again while it's A (B empty) -> deselect A.
    assert app.next_selection("2020-01-01", [0], 0, None, "2020-01-01", None) == (None, None)


def test_selection_click_a_day_deselects_a():
    # Both filled on different days; click A's day -> deselect A only.
    assert app.next_selection("2020-01-01", [0], 0, 5, "2020-01-01", "2020-01-02") == (None, 5)


def test_selection_click_b_day_deselects_b():
    assert app.next_selection("2020-01-02", [5], 0, 5, "2020-01-01", "2020-01-02") == (0, None)


def test_selection_both_on_same_day_clears_both():
    # A=0, B=1 on the same day; clicking that day clears both.
    assert app.next_selection("2020-01-01", [0, 1], 0, 1, "2020-01-01", "2020-01-01") == (
        None,
        None,
    )


def test_selection_both_filled_new_day_restarts():
    assert app.next_selection("2020-03-03", [9], 0, 5, "2020-01-01", "2020-01-02") == (9, None)
