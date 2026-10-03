"""Shared helpers for the community & assets layer (stdlib only).

All fetch scripts write raw records under data/raw/community/<source>/ so the
build step (build_community.py) can re-derive every node/edge and string-match
every quote against stored source text.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "community"
CURATED = ROOT / "data" / "curated"
PIPE = ROOT / "pipeline" / "community"

UA = "rare-disease-atlas/0.1 (hackathon research pipeline; tool=rare-disease-atlas)"

# Slice definition: gene symbol -> disease id + search synonyms.
SLICE = {
    "STXBP1": {"disease": "disease:STXBP1", "terms": ["STXBP1", "Munc18-1", "STXBP1 encephalopathy", "STXBP1-related disorders"]},
    "SYT1": {"disease": "disease:SYT1", "terms": ["SYT1", "Baker-Gordon syndrome", "SYT1-associated neurodevelopmental disorder"]},
    "SNAP25": {"disease": "disease:SNAP25", "terms": ["SNAP25", "SNAP-25", "congenital myasthenic syndrome 18"]},
    "VAMP2": {"disease": "disease:VAMP2", "terms": ["VAMP2", "synaptobrevin-2", "VAMP2-related neurodevelopmental disorder"]},
    "STX1B": {"disease": "disease:STX1B", "terms": ["STX1B", "syntaxin-1B", "GEFS+ type 9"]},
    "SYT2": {"disease": "disease:SYT2", "terms": ["SYT2", "synaptotagmin 2", "presynaptic congenital myasthenic syndrome"]},
    "CPLX1": {"disease": "disease:CPLX1", "terms": ["CPLX1", "complexin 1"]},
    "UNC13A": {"disease": "disease:UNC13A", "terms": ["UNC13A", "Munc13-1"]},
    "STX1A": {"disease": "disease:STX1A", "terms": ["STX1A", "syntaxin-1A"]},
    "NSF": {"disease": "disease:NSF", "terms": ["NSF"]},
    "SLC6A1": {"disease": "disease:SLC6A1", "terms": ["SLC6A1", "GAT-1", "myoclonic-atonic epilepsy"]},
}
GENES = list(SLICE)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def today() -> str:
    return _dt.date.today().isoformat()


_TRANS = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d"})


def slugify(s: str, maxlen: int = 60) -> str:
    s = unicodedata.normalize("NFKD", s.translate(_TRANS)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-")


def redact_emails(text: str) -> str:
    """Strip e-mail addresses (we never store personal contact details)."""
    return EMAIL_RE.sub("[email-redacted]", text)


def _ctx():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http(url: str, data: bytes | None = None, headers: dict | None = None,
         retries: int = 5, backoff: float = 2.0, timeout: int = 60) -> tuple[int, bytes, str]:
    """GET/POST with retry + exponential backoff on 429/5xx. Returns (status, body, final_url)."""
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
                return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                wait = backoff * (2 ** attempt)
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and ra.isdigit():
                    wait = max(wait, int(ra))
                print(f"  HTTP {e.code} on {url[:90]} -> retry in {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            body = e.read() if hasattr(e, "read") else b""
            return e.code, body, url
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            wait = backoff * (2 ** attempt)
            print(f"  {type(e).__name__} on {url[:90]} -> retry in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed after {retries} attempts: {url}: {last_err}")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def read_json(path):
    return json.loads(Path(path).read_text())


def norm_ws(s: str) -> str:
    """Normalise whitespace/quotes/dashes for quote verification."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()
