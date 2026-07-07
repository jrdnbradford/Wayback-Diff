"""Tests for the Wayback Machine client (wayback.py).

Network and disk are stubbed, so these run offline and don't touch the real
cache directory.
"""

import pytest

import wayback
from wayback import Listing, Snapshot

CDX_HEADER = ["timestamp", "original", "mimetype", "statuscode", "digest", "length"]


def make_snap(
    ts="20260101120000",
    original="http://example.com",
    mime="text/html",
    status="200",
    digest="abc",
    length="100",
):
    return Snapshot(
        timestamp=ts,
        original=original,
        mimetype=mime,
        statuscode=status,
        digest=digest,
        length=length,
    )


class FakeResponse:
    def __init__(self, *, json_data=None, text=""):
        self._json = json_data
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def _rows(*data):
    return [CDX_HEADER, *data]


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def test_captured_at_parses_timestamp():
    dt = make_snap(ts="20250607083000").captured_at
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (
        2025,
        6,
        7,
        8,
        30,
        0,
    )


def test_captured_at_invalid_returns_none():
    assert make_snap(ts="not-a-timestamp").captured_at is None


def test_label_format():
    s = make_snap(ts="20250607083000", status="200", mime="text/html")
    assert s.label == "2025-06-07 08:30:00 UTC  ·  200  ·  text/html"


def test_archive_and_raw_urls():
    s = make_snap(ts="20250101000000", original="http://x.com/")
    assert s.archive_url == "https://web.archive.org/web/20250101000000/http://x.com/"
    # raw url gets the id_ suffix for un-rewritten original bytes
    assert s.raw_url == "https://web.archive.org/web/20250101000000id_/http://x.com/"


# --------------------------------------------------------------------------- #
# list_snapshots
# --------------------------------------------------------------------------- #
def test_list_snapshots_parses_newest_first(monkeypatch):
    rows = _rows(
        ["20200101000000", "http://x", "text/html", "200", "d1", "10"],
        ["20210101000000", "http://x", "text/html", "200", "d2", "20"],
    )
    monkeypatch.setattr(wayback.requests, "get", lambda *a, **k: FakeResponse(json_data=rows))
    listing = wayback.list_snapshots("http://x", limit=50)
    assert isinstance(listing, Listing)
    assert [s.timestamp for s in listing.snapshots] == [
        "20210101000000",
        "20200101000000",
    ]
    assert listing.fetched == 2
    assert listing.limit == 50
    assert listing.more_exist is False


def test_list_snapshots_more_exist_when_page_full(monkeypatch):
    rows = _rows(
        ["20200101000000", "http://x", "text/html", "200", "d1", "10"],
        ["20210101000000", "http://x", "text/html", "200", "d2", "20"],
    )
    monkeypatch.setattr(wayback.requests, "get", lambda *a, **k: FakeResponse(json_data=rows))
    listing = wayback.list_snapshots("http://x", limit=2)
    assert listing.more_exist is True


def test_list_snapshots_empty(monkeypatch):
    monkeypatch.setattr(wayback.requests, "get", lambda *a, **k: FakeResponse(json_data=[]))
    listing = wayback.list_snapshots("http://x", limit=5)
    assert listing.snapshots == []
    assert listing.fetched == 0
    assert listing.more_exist is False


def test_list_snapshots_keeps_redirects_and_revisits(monkeypatch):
    # No filtering: redirect stubs and revisit records must be preserved.
    rows = _rows(
        ["20200101000000", "http://x", "text/html", "200", "d1", "10"],
        ["20200201000000", "http://x", "unk", "301", "d2", "0"],
        ["20200301000000", "http://x", "warc/revisit", "-", "d1", "0"],
    )
    monkeypatch.setattr(wayback.requests, "get", lambda *a, **k: FakeResponse(json_data=rows))
    listing = wayback.list_snapshots("http://x", limit=50)
    assert listing.fetched == 3
    assert len(listing.snapshots) == 3
    mimes = {s.mimetype for s in listing.snapshots}
    assert {"unk", "warc/revisit"} <= mimes


def test_list_snapshots_requests_most_recent_via_negative_limit(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return FakeResponse(json_data=[CDX_HEADER])

    monkeypatch.setattr(wayback.requests, "get", fake_get)
    wayback.list_snapshots("http://x", limit=7)
    assert captured["params"]["limit"] == "-7"


# --------------------------------------------------------------------------- #
# Disk cache
# --------------------------------------------------------------------------- #
@pytest.fixture
def disk_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a temp dir for the duration of a test."""
    monkeypatch.setattr(wayback, "CACHE_DIR", tmp_path / "snapshots")
    return tmp_path


def test_fetch_content_caches_on_disk_and_survives_restart(disk_cache, monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResponse(text="<html>hi</html>")

    monkeypatch.setattr(wayback.requests, "get", fake_get)
    snap = make_snap()

    assert wayback.is_cached(snap) is False
    assert wayback.fetch_content(snap) == "<html>hi</html>"
    assert calls["n"] == 1
    assert wayback.is_cached(snap) is True

    # There is no in-memory cache, so a second call reads purely from disk --
    # this is exactly what a fresh process (app restart) would do. No new GET.
    assert wayback.fetch_content(snap) == "<html>hi</html>"
    assert calls["n"] == 1


def test_fetch_content_use_disk_false_never_caches(disk_cache, monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResponse(text="x")

    monkeypatch.setattr(wayback.requests, "get", fake_get)
    snap = make_snap()

    wayback.fetch_content(snap, use_disk=False)
    wayback.fetch_content(snap, use_disk=False)
    assert calls["n"] == 2  # fetched fresh both times
    assert wayback.is_cached(snap, use_disk=False) is False
    assert not wayback._disk_path(snap.raw_url).exists()


def test_clear_disk_cache(disk_cache, monkeypatch):
    monkeypatch.setattr(wayback.requests, "get", lambda *a, **k: FakeResponse(text="x"))
    snap = make_snap()
    wayback.fetch_content(snap)
    assert wayback.is_cached(snap) is True
    assert wayback.clear_disk_cache() == 1
    assert wayback.is_cached(snap) is False


def test_clear_disk_cache_when_empty(disk_cache):
    assert wayback.clear_disk_cache() == 0


# --------------------------------------------------------------------------- #
# html_to_text
# --------------------------------------------------------------------------- #
def test_html_to_text_strips_tags_scripts_styles():
    html_in = (
        "<html><head><style>.x{color:red}</style>"
        "<script>var a=1;</script></head>"
        "<body><h1>Title</h1><p>Hello world</p></body></html>"
    )
    text = wayback.html_to_text(html_in)
    assert "Title" in text
    assert "Hello world" in text
    assert "color:red" not in text
    assert "var a=1" not in text


def test_html_to_text_decodes_entities():
    assert wayback.html_to_text("<p>a &amp; b &lt;c&gt;</p>") == "a & b <c>"
