"""Shared helpers for the DEE (channels / receptors / signalling DEEs) community sub-layer.

Stdlib only. Everything fetched is stored under data/raw/families/dee/community/ so the
build (build_fragment.py) and the verifier (verify_community.py) can re-derive every node
and string-match every quote offline.

- Web pages: direct fetch first, Bright Data Web Unlocker only as a fallback. The Bright Data
  cache is redirected into our own raw dir, and every non-cached request is logged to
  bd_usage.json (budget: 100 requests).
- NCBI E-utilities go through pipeline/biology/common.py eutils() (shared cross-process
  throttle, tool=rare-disease-atlas, no email param, 429 backoff).
- E-mail addresses are redacted from everything saved.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PIPE = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "families" / "dee" / "community"
WEB = RAW / "web"
CTGOV = RAW / "ctgov"
REPORTER = RAW / "reporter"
PUBMED = RAW / "pubmed"
BD_CACHE = RAW / "brightdata"
BD_LOG = RAW / "bd_usage.json"
BD_BUDGET = 100
FAMILY = "dee"

UA = "rare-disease-atlas/0.1 (hackathon research pipeline; tool=rare-disease-atlas)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36 rare-disease-atlas/0.1")

# gene -> regex that names the gene (symbol or protein alias) and regex for the gene-defined syndrome(s)
GENES = {
    "SCN1A": {"gene_rx": r"\bSCN1A\b|\bNav1\.1\b",
              "syn_rx": r"\bDravet\b|severe myoclonic epilepsy of infancy|\bSMEI\b",
              "syndromes": ["Dravet syndrome"]},
    "SCN2A": {"gene_rx": r"\bSCN2A\b|\bNav1\.2\b", "syn_rx": r"(?!x)x", "syndromes": ["SCN2A-related disorders"]},
    "SCN8A": {"gene_rx": r"\bSCN8A\b|\bNav1\.6\b", "syn_rx": r"(?!x)x", "syndromes": ["SCN8A-related disorders"]},
    "KCNQ2": {"gene_rx": r"\bKCNQ2\b|\bKv7\.2\b", "syn_rx": r"(?!x)x",
              "syndromes": ["KCNQ2-DEE", "self-limited neonatal epilepsy"]},
    "KCNT1": {"gene_rx": r"\bKCNT1\b|\bKNa1\.1\b|\bSlack\b",
              "syn_rx": r"epilepsy of infancy with migrating focal seizures|malignant migrating partial seizures|\bEIMFS\b|\bMMPSI\b",
              "syndromes": ["EIMFS", "ADNFLE"]},
    "CACNA1A": {"gene_rx": r"\bCACNA1A\b|\bCav2\.1\b",
                "syn_rx": r"episodic ataxia,? type 2|\bEA2\b|familial hemiplegic migraine(,? type)? ?1|\bFHM1\b",
                "syndromes": ["episodic ataxia type 2", "familial hemiplegic migraine type 1"]},
    "GRIN2B": {"gene_rx": r"\bGRIN2B\b|\bGluN2B\b", "syn_rx": r"(?!x)x", "syndromes": ["GRIN2B-related disorders"]},
    "CDKL5": {"gene_rx": r"\bCDKL5\b", "syn_rx": r"(?!x)x", "syndromes": ["CDKL5 deficiency disorder"]},
    "SYNGAP1": {"gene_rx": r"\bSYNGAP1?\b", "syn_rx": r"(?!x)x", "syndromes": ["SYNGAP1-related intellectual disability"]},
    "SLC2A1": {"gene_rx": r"\bSLC2A1\b",
               "syn_rx": r"GLUT-?1 deficiency|\bGLUT-?1 ?DS\b|\bG1D\b|De ?Vivo (disease|syndrome)|glucose transporter (type )?1 deficiency",
               "syndromes": ["GLUT1 deficiency syndrome"]},
}
GENE_LIST = list(GENES)
GENE_RX = {g: re.compile(v["gene_rx"], re.I if g not in ("KCNT1", "SYNGAP1") else 0) for g, v in GENES.items()}
GENE_RX["SYNGAP1"] = re.compile(r"\bSYNGAP1?\b|\bSynGAP\b", re.I)
GENE_RX["KCNT1"] = re.compile(r"\bKCNT1\b|\bKNa1\.1\b", re.I)
SYN_RX = {g: re.compile(v["syn_rx"], re.I) for g, v in GENES.items()}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def today() -> str:
    return _dt.date.today().isoformat()


_TRANS = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d"})


def slugify(s: str, maxlen: int = 60) -> str:
    """Identical to pipeline/community/common.py slugify (so researcher ids line up)."""
    s = unicodedata.normalize("NFKD", s.translate(_TRANS)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-")


def redact_emails(text: str) -> str:
    return EMAIL_RE.sub("[email-redacted]", text)


def norm(s: str) -> str:
    """Quote-matching normalisation: NFKC, fold curly quotes / dashes / nbsp / zero-width, collapse whitespace."""
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("′", "'").replace("´", "'"))
    for d in ("‐", "‑", "‒", "–", "—", "―", "−"):
        s = s.replace(d, "-")
    s = s.replace(" ", " ").replace("​", "").replace("‌", "").replace("‍", "").replace("﻿", "")
    return re.sub(r"\s+", " ", s).strip()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def _ctx():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http(url: str, data: bytes | None = None, headers: dict | None = None,
         retries: int = 4, backoff: float = 2.0, timeout: int = 45) -> tuple[int, bytes, str]:
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
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and ra.isdigit():
                    wait = max(wait, int(ra))
                print(f"  HTTP {e.code} on {url[:90]} -> retry in {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            body = e.read() if hasattr(e, "read") else b""
            return e.code, body, url
        except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"failed after {retries} attempts: {url}: {last_err}")


# ---------------------------------------------------------------- Bright Data (budgeted)
def _bd():
    sys.path.insert(0, str(ROOT / "pipeline"))
    import brightdata  # noqa: E402
    brightdata.CACHE_DIR = BD_CACHE  # keep the cache inside our family directory
    return brightdata


def bd_used() -> list:
    return read_json(BD_LOG) if BD_LOG.exists() else []


def _bd_cache_file(bd, zone_key: str, url: str, kind: str) -> Path:
    cfg = bd._config()
    zone = cfg[zone_key]
    return BD_CACHE / kind / (hashlib.sha256(f"{zone}|{url}".encode()).hexdigest()[:24] + ".json")


def _bd_log(kind: str, url: str, ok: bool, err: str | None = None):
    log = bd_used()
    log.append({"kind": kind, "url": url, "date": today(), "ok": ok, **({"error": err[:200]} if err else {})})
    write_json(BD_LOG, log)


def bd_fetch(url: str) -> dict | None:
    """Web Unlocker fetch, cached; refuses to exceed the request budget."""
    bd = _bd()
    cached = _bd_cache_file(bd, "unlocker_zone", url, "unlocker").exists()
    if not cached and len(bd_used()) >= BD_BUDGET:
        print(f"  Bright Data budget exhausted; skipping {url}", file=sys.stderr)
        return None
    try:
        rec = bd.fetch(url)
        if not cached:
            _bd_log("unlocker", url, True)
        return rec
    except Exception as e:  # noqa: BLE001
        if not cached:
            _bd_log("unlocker", url, False, str(e))
        print(f"  Bright Data fetch failed for {url}: {e}", file=sys.stderr)
        return None


def bd_search(query: str, num: int = 10) -> list | None:
    bd = _bd()
    import urllib.parse
    params = urllib.parse.urlencode({"q": query, "num": num, "hl": "en", "gl": "us", "brd_json": 1})
    cached = _bd_cache_file(bd, "serp_zone", f"https://www.google.com/search?{params}", "serp").exists()
    if not cached and len(bd_used()) >= BD_BUDGET:
        print(f"  Bright Data budget exhausted; skipping search {query!r}", file=sys.stderr)
        return None
    try:
        res = bd.search(query, num=num)
        if not cached:
            _bd_log("serp", query, True)
        return res
    except Exception as e:  # noqa: BLE001
        if not cached:
            _bd_log("serp", query, False, str(e))
        print(f"  Bright Data search failed for {query!r}: {e}", file=sys.stderr)
        return None
