"""Shared helpers for the biology pipeline (stdlib only).

- Every remote response is cached under data/raw/biology/ so the dataset can be
  rebuilt offline and every claim can be traced to the exact payload we saw.
- NCBI E-utilities calls are throttled to <= 2 requests/second ACROSS processes
  (file lock), carry tool=rare-disease-atlas, never send an email param, and
  retry with exponential backoff on 429/5xx.
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "biology"
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
CURATED = ROOT / "data" / "curated"
RAW.mkdir(parents=True, exist_ok=True)

TODAY = _dt.date.today().isoformat()
UA = "rare-disease-atlas/0.1 (hackathon research pipeline)"
NCBI_TOOL = "rare-disease-atlas"
_NCBI_LOCK = RAW / ".ncbi_throttle"
_NCBI_MIN_INTERVAL = 0.55  # seconds => < 2 req/s

# Gene slice
CORE_GENES = ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B"]
EXTENDED_CANDIDATES = ["SYT2", "CPLX1", "UNC13A", "STX1A", "NSF"]
BRIDGE_GENES = ["SLC6A1"]
ALL_GENES = CORE_GENES + EXTENDED_CANDIDATES + BRIDGE_GENES


def _ncbi_wait() -> None:
    """Cross-process throttle: at most one NCBI request every 0.55 s."""
    _NCBI_LOCK.touch(exist_ok=True)
    with open(_NCBI_LOCK, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            raw = fh.read().strip()
            last = float(raw) if raw else 0.0
            wait = last + _NCBI_MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            fh.seek(0)
            fh.truncate()
            fh.write(str(time.time()))
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def http_get(url: str, params: dict | None = None, headers: dict | None = None,
             data: bytes | None = None, retries: int = 6, timeout: int = 60,
             ncbi: bool = False) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    delay = 1.5
    last_err: Exception | None = None
    for attempt in range(retries):
        if ncbi:
            _ncbi_wait()
        req = urllib.request.Request(url, headers=hdrs, data=data)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After") if e.headers else None
                sleep_for = float(ra) if ra and ra.isdigit() else delay
                time.sleep(sleep_for)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GET failed after {retries} attempts: {url} :: {last_err}")


def cached_json(cache_path: pathlib.Path, url: str, params: dict | None = None,
                headers: dict | None = None, refresh: bool = False, ncbi: bool = False,
                data: bytes | None = None):
    """Fetch JSON (or reuse the cached raw payload). Cache stores the raw response."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())
    body = http_get(url, params=params, headers=headers, ncbi=ncbi, data=data)
    obj = json.loads(body)
    cache_path.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    return obj


def cached_text(cache_path: pathlib.Path, url: str, params: dict | None = None,
                headers: dict | None = None, refresh: bool = False, ncbi: bool = False) -> str:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not refresh:
        return cache_path.read_text()
    body = http_get(url, params=params, headers=headers, ncbi=ncbi).decode("utf-8")
    cache_path.write_text(body)
    return body


def eutils(endpoint: str, params: dict) -> bytes:
    """NCBI E-utilities call with the shared throttle. Never sends an email param."""
    p = dict(params)
    p.pop("email", None)
    p["tool"] = NCBI_TOOL
    return http_get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/{endpoint}", params=p, ncbi=True)


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path: pathlib.Path):
    return json.loads(path.read_text())


def evidence(source: str, ref: str, url: str, kind: str, extracted_by: str = "database",
             title: str | None = None, year: int | None = None, quote: str | None = None,
             study_type: str | None = None, supports: bool | None = None,
             verified: bool | None = None, retrieved: str | None = None) -> dict:
    ev = {"source": source, "ref": ref, "url": url}
    if title:
        ev["title"] = title
    if year:
        ev["year"] = int(year)
    if quote:
        ev["quote"] = quote
    ev["kind"] = kind
    if study_type:
        ev["study_type"] = study_type
    if supports is not None:
        ev["supports"] = supports
    ev["extracted_by"] = extracted_by
    if verified is not None:
        ev["verified"] = verified
    ev["retrieved"] = retrieved or TODAY
    return ev


def edge_id(source: str, etype: str, target: str) -> str:
    return f"{source}|{etype}|{target}"
