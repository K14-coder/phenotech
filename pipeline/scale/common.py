"""Shared helpers for the BREADTH (scale) community layer. Stdlib only.

Writes ONLY under data/raw/scale/ (cached raw data) and data/derived/scale/ (outputs).

Bright Data: we reuse pipeline/brightdata.py (search() / fetch()) but redirect its cache to
data/raw/scale/brightdata/ and count every live (uncached) request against a hard budget.
Responses already cached by the deep layer in data/raw/brightdata/ are re-used read-only.
The API token is read by brightdata.py from .env.local and is never printed or logged here.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import re
import shutil
import ssl
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "scale"
OUT = ROOT / "data" / "derived" / "scale"
DL = ROOT / "data" / "raw" / "downloads"
GLOBAL_INDEX = ROOT / "data" / "derived" / "global" / "index.json"
GRAPH = ROOT / "data" / "graph.json"

UA = "rare-disease-atlas/0.1 (hackathon research pipeline; tool=rare-disease-atlas)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

BD_BUDGET = 1200  # live Bright Data requests (SERP + unlocker) for the whole task


def today() -> str:
    return _dt.date.today().isoformat()


def write_json(path: Path, obj, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent, ensure_ascii=False))
    tmp.replace(path)


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    if p.suffix == ".gz":
        with gzip.open(p, "rt") as f:
            return json.load(f)
    return json.loads(p.read_text())


def write_json_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


_TRANS = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A", "ß": "ss",
                        "ł": "l", "Ł": "L", "đ": "d"})


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s.translate(_TRANS)).encode("ascii", "ignore").decode()


def slugify(s: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_fold(s)).strip("-").lower()
    return s[:maxlen].strip("-")


def norm_ws(s: str) -> str:
    """Whitespace/quote/dash normalisation used for verbatim-quote verification."""
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-").replace(" ", " ").replace("​", ""))
    return re.sub(r"\s+", " ", s).strip()


_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8",
          "ix": "9", "x": "10", "xi": "11", "xii": "12"}


def norm_text(s: str) -> str:
    """Token normalisation for name matching: ascii-fold, lowercase, drop possessive 's,
    punctuation -> space, roman numerals after 'type'/'class'/'group' -> arabic."""
    s = ascii_fold(norm_ws(s)).lower()
    s = re.sub(r"(\w)'s\b", r"\1s", s)          # Gaucher's -> gauchers
    s = re.sub(r"(\w)s'\b", r"\1s", s)
    s = re.sub(r"(\w)'(\w)", r"\1\2", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = s.split()
    out = []
    for i, t in enumerate(toks):
        if t in _ROMAN and i > 0 and toks[i - 1] in ("type", "class", "group", "grade", "form"):
            t = _ROMAN[t]
        out.append(t)
    # "gauchers disease" and "gaucher disease" should meet: drop trailing possessive s on
    # the token before disease/syndrome only when the bare form is >= 4 chars
    for i in range(len(out) - 1):
        if out[i + 1] in ("disease", "syndrome", "disorder", "dystrophy", "ataxia", "anemia", "anaemia") \
                and out[i].endswith("s") and len(out[i]) > 4 and not out[i].endswith("ss"):
            out[i] = out[i][:-1] if out[i][:-1] + "s" == out[i] else out[i]
    return " ".join(out)


def deinvert(s: str) -> list[str]:
    """MeSH/OMIM-style inverted names: 'Muscular Dystrophy, Duchenne' -> 'Duchenne Muscular Dystrophy';
    'Cardiomyopathy, familial hypertrophic, 1' -> 'familial hypertrophic Cardiomyopathy 1'."""
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) == 2:
        return [f"{parts[1]} {parts[0]}"]
    if len(parts) == 3 and re.fullmatch(r"(type\s+)?[0-9]+[a-z]?|[ivx]+|[a-z]", parts[2], re.I):
        return [f"{parts[1]} {parts[0]} {parts[2]}"]
    return []


# --------------------------------------------------------------------------- HTTP
def _ctx():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http(url: str, headers: dict | None = None, retries: int = 5, backoff: float = 2.0,
         timeout: int = 60, quiet_codes=(404,)) -> tuple[int, bytes, str]:
    """GET with exponential backoff on 429/5xx (honours Retry-After). Returns (status, body, final_url)."""
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
                return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                wait = backoff * (2 ** attempt)
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and ra.isdigit():
                    wait = max(wait, int(ra))
                print(f"  HTTP {e.code} -> retry in {wait:.0f}s ({url[:80]})", file=sys.stderr)
                time.sleep(wait)
                continue
            try:
                body = e.read()
            except Exception:
                body = b""
            return e.code, body, url
        except Exception as e:  # URLError, timeouts, connection resets, SSL
            last = e
            if attempt >= 2:
                break
            time.sleep(backoff * (2 ** attempt))
    return 0, str(last).encode(), url


def fetch_direct(url: str, timeout: int = 25) -> tuple[int, str, str]:
    """Plain (free) fetch with a browser UA; no retries beyond 2. Returns (status, text, final_url)."""
    st, body, final = http(url, headers={"User-Agent": BROWSER_UA,
                                         "Accept": "text/html,application/xhtml+xml"},
                           retries=2, backoff=1.0, timeout=timeout)
    return st, body.decode("utf-8", errors="replace"), final


# --------------------------------------------------------------------------- HTML -> text
_TAG_BLOCK = re.compile(r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>", re.S | re.I)
_BR = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr|/td|/th|p|li|h[1-6]|tr)[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def html_to_text(html: str) -> str:
    import html as _h
    s = _TAG_BLOCK.sub(" ", html)
    s = _BR.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = _h.unescape(s)
    s = EMAIL_RE.sub("[email-redacted]", s)
    lines = [norm_ws(l) for l in s.split("\n")]
    return "\n".join(l for l in lines if l)


def domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- Bright Data
sys.path.insert(0, str(ROOT / "pipeline"))
import brightdata as _bd  # noqa: E402

BD_CACHE = RAW / "brightdata"
_bd.CACHE_DIR = BD_CACHE  # redirect the shared client's cache into our own write area
LEGACY_BD_CACHE = ROOT / "data" / "raw" / "brightdata"
BD_LOG = RAW / "brightdata_usage.jsonl"
_bd_lock = threading.Lock()


def _bd_cache_file(base: Path, zone: str, url: str, kind: str) -> Path:
    return base / kind / (hashlib.sha256(f"{zone}|{url}".encode()).hexdigest()[:24] + ".json")


def bd_live_count() -> int:
    if not BD_LOG.exists():
        return 0
    return sum(1 for l in BD_LOG.read_text().splitlines() if l.strip())


def _bd_prepare(zone: str, url: str, kind: str) -> bool:
    """True if served from cache (ours or the deep layer's, copied in)."""
    mine = _bd_cache_file(BD_CACHE, zone, url, kind)
    if mine.exists():
        return True
    legacy = _bd_cache_file(LEGACY_BD_CACHE, zone, url, kind)
    if legacy.exists():
        mine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(legacy, mine)
        return True
    return False


def _bd_log(kind: str, target: str, ok: bool, note: str = ""):
    with _bd_lock:
        BD_LOG.parent.mkdir(parents=True, exist_ok=True)
        with BD_LOG.open("a") as f:
            f.write(json.dumps({"t": _dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
                                "target": target[:300], "ok": ok, "note": note[:200]}) + "\n")


class BudgetExceeded(RuntimeError):
    pass


def bd_search(query: str, num: int = 10, attempts: int = 2) -> list[dict]:
    """SERP via brightdata.search(). brightdata.py caches the raw body before parsing, so a transient
    non-JSON answer would be cached forever: we delete such a cache entry and retry (each retry is a
    live request and is counted)."""
    cfg = _bd._config()
    params = urllib.parse.urlencode({"q": query, "num": num, "hl": "en", "gl": "us", "brd_json": 1})
    url = f"https://www.google.com/search?{params}"
    cache_file = _bd_cache_file(BD_CACHE, cfg["serp_zone"], url, "serp")
    if _bd_prepare(cfg["serp_zone"], url, "serp"):
        try:
            return _bd.search(query, num=num)
        except RuntimeError:
            cache_file.unlink(missing_ok=True)  # bad cached body: refetch below
    last = None
    for _ in range(attempts):
        if bd_live_count() >= BD_BUDGET:
            raise BudgetExceeded("Bright Data budget reached")
        try:
            res = _bd.search(query, num=num)
            _bd_log("serp", query, True)
            return res
        except Exception as e:
            last = e
            _bd_log("serp", query, False, str(e).split(":")[0])
            cache_file.unlink(missing_ok=True)
            time.sleep(2)
    raise RuntimeError(f"SERP failed: {str(last)[:80]}")


def bd_fetch(url: str) -> dict:
    cfg = _bd._config()
    if not _bd_prepare(cfg["unlocker_zone"], url, "unlocker"):
        if bd_live_count() >= BD_BUDGET:
            raise BudgetExceeded("Bright Data budget reached")
        try:
            res = _bd.fetch(url)
        except Exception as e:
            _bd_log("unlocker", url, False, str(e).split(":")[0])
            raise
        _bd_log("unlocker", url, True)
        return res
    return _bd.fetch(url)


def bd_cached(url: str) -> bool:
    cfg = _bd._config()
    return _bd_prepare(cfg["unlocker_zone"], url, "unlocker")


# --------------------------------------------------------------------------- page store
PAGES = RAW / "pages"


def page_path(url: str) -> Path:
    return PAGES / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def get_page(url: str, allow_bd: bool = True, prefer_bd: bool = False) -> dict | None:
    """Fetch a page once (direct first, Bright Data unlocker as fallback) and store
    {url, final_url, retrieved, via, status, text} in data/raw/scale/pages/. Text has e-mails redacted."""
    p = page_path(url)
    if p.exists():
        return json.loads(p.read_text())
    rec = None
    if not prefer_bd:
        st, html, final = fetch_direct(url)
        if st == 200 and len(html) > 500 and not _looks_blocked(html):
            rec = {"url": url, "final_url": final, "retrieved": today(), "via": "direct", "status": st,
                   "text": html_to_text(html), "html_len": len(html)}
            _save_html(url, html)
    if rec is None and allow_bd:
        try:
            r = bd_fetch(url)
            html = r["html"]
            if html and len(html) > 200:
                rec = {"url": url, "final_url": url, "retrieved": r["retrieved"], "via": "brightdata",
                       "status": 200, "text": html_to_text(html), "html_len": len(html)}
                _save_html(url, html)
        except BudgetExceeded:
            raise
        except Exception as e:
            rec = {"url": url, "final_url": url, "retrieved": today(), "via": "error", "status": 0,
                   "text": "", "error": str(e)[:200]}
    if rec is None:
        rec = {"url": url, "final_url": url, "retrieved": today(), "via": "error", "status": 0, "text": ""}
    write_json(p, rec)
    return rec


def _save_html(url: str, html: str):
    hp = PAGES / "html" / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html.gz")
    hp.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(hp, "wt") as f:
        f.write(EMAIL_RE.sub("[email-redacted]", html))


def get_html(url: str) -> str | None:
    hp = PAGES / "html" / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html.gz")
    if hp.exists():
        with gzip.open(hp, "rt") as f:
            return f.read()
    return None


def _looks_blocked(html: str) -> bool:
    h = html[:5000].lower()
    return any(k in h for k in ("cf-browser-verification", "just a moment...", "attention required! | cloudflare",
                                "access denied", "captcha", "are you a robot", "enable javascript and cookies"))
