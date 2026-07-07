"""Internet Archive Wayback Machine client.

Thin wrapper over the public CDX Server API (snapshot listing) and the raw
snapshot endpoint (per-version content retrieval). No API key required.

Docs: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
# The `id_` suffix returns the *original* archived bytes with no Wayback
# rewriting or toolbar injection -- essential for a meaningful diff.
SNAPSHOT_TEMPLATE = "https://web.archive.org/web/{timestamp}id_/{url}"

# Fields we request from the CDX API, in order.
CDX_FIELDS = ["timestamp", "original", "mimetype", "statuscode", "digest", "length"]

_HEADERS = {"User-Agent": "Wayback-Diff/1.0 (+Shiny app; contact via app)"}
_TIMEOUT = 60


@dataclass(frozen=True)
class Snapshot:
    """One archived capture of a URL."""

    timestamp: str  # 14-digit YYYYMMDDhhmmss
    original: str
    mimetype: str
    statuscode: str
    digest: str
    length: str

    @property
    def captured_at(self) -> datetime | None:
        try:
            return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    @property
    def label(self) -> str:
        dt = self.captured_at
        when = dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else self.timestamp
        return f"{when}  ·  {self.statuscode}  ·  {self.mimetype}"

    @property
    def archive_url(self) -> str:
        """Human-viewable snapshot (with the Wayback toolbar)."""
        return f"https://web.archive.org/web/{self.timestamp}/{self.original}"

    @property
    def raw_url(self) -> str:
        """Raw original bytes, suitable for diffing."""
        return SNAPSHOT_TEMPLATE.format(timestamp=self.timestamp, url=self.original)


@dataclass(frozen=True)
class Listing:
    """Result of a snapshot query. Every capture the CDX API returns is kept --
    no merging or filtering -- so ``fetched`` equals ``len(snapshots)``."""

    snapshots: list[Snapshot]
    fetched: int  # capture rows CDX returned (== number shown)
    limit: int  # the requested "Max snapshots"

    @property
    def more_exist(self) -> bool:
        """True if CDX returned a full page, so older captures were left off."""
        return self.fetched >= self.limit


def list_snapshots(
    url: str,
    *,
    limit: int = 200,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Listing:
    """Return a :class:`Listing` of snapshots of ``url``, newest first.

    Every capture is returned as-is -- no collapsing of identical captures and
    no filtering of redirect/revisit records. When more captures exist than
    ``limit``, the *most recent* ``limit`` are returned.
    """
    # A negative limit tells the CDX API to return the *most recent* N captures
    # (the tail) rather than the oldest N, so the default view is up to date.
    params: dict[str, str] = {
        "url": url.strip(),
        "output": "json",
        "fl": ",".join(CDX_FIELDS),
        "limit": str(-abs(limit)),
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    resp = requests.get(CDX_ENDPOINT, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return Listing([], fetched=0, limit=limit)

    # First row is the header; map by name so field order can't bite us.
    header = rows[0]
    idx = {name: header.index(name) for name in CDX_FIELDS if name in header}

    snapshots = [
        Snapshot(**{name: row[pos] for name, pos in idx.items()}) for row in rows[1:]
    ]
    # CDX returns oldest-first; present newest-first.
    snapshots.reverse()
    return Listing(snapshots=snapshots, fetched=len(snapshots), limit=limit)


# An archived capture is immutable, so its content never changes for a given
# raw URL -- safe to cache. Caching is a single on-disk layer (``use_disk``)
# that persists across restarts; there is no in-memory/session cache.


def _default_cache_dir() -> Path:
    """Per-OS user cache directory for persisted snapshot pages."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "wayback-diff" / "snapshots"


CACHE_DIR: Path = _default_cache_dir()


def _disk_path(raw_url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(raw_url.encode()).hexdigest() + ".txt")


def fetch_content(snapshot: Snapshot, *, use_disk: bool = True) -> str:
    """Fetch the raw archived content of a snapshot as text.

    When ``use_disk`` is set (the default), a persistent on-disk copy is
    read/written so the content survives restarts. With ``use_disk=False`` the
    page is always downloaded fresh and nothing is cached.
    """
    url = snapshot.raw_url

    if use_disk:
        path = _disk_path(url)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                pass  # unreadable/corrupt cache file -> fall through and refetch

    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
    text = resp.text

    if use_disk:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _disk_path(url).write_text(text, encoding="utf-8")
        except OSError:
            pass  # best-effort persistence
    return text


def is_cached(snapshot: Snapshot, *, use_disk: bool = True) -> bool:
    """True if the content is already on disk (no network fetch needed)."""
    return bool(use_disk and _disk_path(snapshot.raw_url).exists())


def clear_disk_cache() -> int:
    """Delete all persisted snapshot pages. Returns the number of files removed."""
    if not CACHE_DIR.exists():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.txt"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_WS_RE = re.compile(r"[ \t]+")


def html_to_text(html: str) -> str:
    """Crude HTML -> visible-text reduction for a readable diff.

    Not a full parser -- just enough to strip markup, scripts, and styles so
    the diff reflects content changes rather than markup churn.
    """
    text = _SCRIPT_STYLE_RE.sub("", html)
    text = _TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    # Collapse runs of blank lines.
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()
