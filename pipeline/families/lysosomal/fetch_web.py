"""Evidence store for the lysosomal family's patient organisations and registries.

Reads pipeline/families/lysosomal/web_sources.json, a list of
    {"id": "<short-slug>", "url": "https://...", "via": "direct" | "brightdata"}
and stores every page as
    data/raw/families/lysosomal/web/<id>.html   (raw HTML, e-mail addresses redacted)
    data/raw/families/lysosomal/web/<id>.txt    (lyso_common.html_to_text, e-mail addresses redacted)
plus data/raw/families/lysosomal/web/_manifest.json
    {id: {url, final_url, status, via, retrieved, text_chars}}.

Every quote in curated_orgs.json must string-match the stored <id>.txt (check_orgs.py enforces it),
so this script is the only place web evidence comes from. Direct fetch first (urllib, browser
User-Agent, 40 s timeout); via=brightdata uses lyso_common.bd_fetch (cached, budget-counted) for
sites that block direct fetches or render empty.

Usage:
  python3 pipeline/families/lysosomal/fetch_web.py                # fetch ids not yet stored with status 200
  python3 pipeline/families/lysosomal/fetch_web.py --refresh      # re-fetch everything
  python3 pipeline/families/lysosomal/fetch_web.py --only a,b     # (re-)fetch selected ids
  python3 pipeline/families/lysosomal/fetch_web.py --grep 'regex' [--only a,b]   # search stored text
"""
from __future__ import annotations

import argparse
import gzip
import http.cookiejar
import re
import sys
import time
import urllib.error
import urllib.request
import zlib

import lyso_common as lc

SRC = lc.HERE / "web_sources.json"
OUT = lc.WEB_DIR
MANIFEST = OUT / "_manifest.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
BLOCKED = re.compile(r"(Access denied|403 Forbidden|Just a moment\.\.\.|Attention Required! \| Cloudflare|"
                     r"Enable JavaScript and cookies to continue)", re.I)


def _decode(body: bytes, headers) -> str:
    enc = (headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    elif enc == "deflate":
        body = zlib.decompress(body)
    m = re.search(r"charset=([\w-]+)", headers.get("Content-Type") or "", re.I)
    charset = m.group(1) if m else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _save(sid: str, raw_html: str) -> int:
    raw_html = lc.redact_emails(raw_html)
    (OUT / f"{sid}.html").write_text(raw_html)
    text = lc.redact_emails(lc.html_to_text(raw_html))
    (OUT / f"{sid}.txt").write_text(text)
    return len(text)


def fetch_direct(sid: str, url: str, retries: int = 2) -> dict:
    last_err = None
    # a cookie jar per page: some sites answer the first request with a cookie-setting redirect
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"})
        try:
            with opener.open(req, timeout=40) as resp:
                raw = _decode(resp.read(), resp.headers)
                status, final = resp.status, resp.geturl()
            chars = _save(sid, raw)
            if BLOCKED.search(raw[:4000]) and chars < 2000:
                status = 0  # a bot wall, not the page
            return {"url": url, "final_url": final, "status": status, "via": "direct",
                    "retrieved": lc.TODAY, "text_chars": chars}
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (403, 404, 410, 451):
                return {"url": url, "final_url": url, "status": e.code, "via": "direct",
                        "retrieved": lc.TODAY, "text_chars": 0, "error": last_err}
        except Exception as e:  # noqa: BLE001 - network failure: record it, keep going
            last_err = str(e)[:200]
        time.sleep(2 * (attempt + 1))
    return {"url": url, "final_url": url, "status": None, "via": "direct", "retrieved": lc.TODAY,
            "text_chars": 0, "error": last_err}


def fetch_bd(sid: str, url: str) -> dict:
    try:
        rec = lc.bd_fetch(url)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "final_url": url, "status": None, "via": "brightdata", "retrieved": lc.TODAY,
                "text_chars": 0, "error": str(e)[:200]}
    raw = rec.get("html") or ""
    chars = _save(sid, raw)
    ok = len(raw) > 500 and not (BLOCKED.search(raw[:4000]) and chars < 2000)
    return {"url": url, "final_url": url, "status": 200 if ok else 0, "via": "brightdata",
            "retrieved": rec.get("retrieved", lc.TODAY), "text_chars": chars}


def grep(pattern: str, ids: list[str] | None, width: int = 220) -> None:
    rx = re.compile(pattern, re.I)
    for f in sorted(OUT.glob("*.txt")):
        if ids and f.stem not in ids:
            continue
        t = lc.norm(f.read_text())
        hits = list(rx.finditer(t))
        if not hits:
            continue
        print(f"--- {f.stem} ({len(hits)} hits)")
        last = -1
        for m in hits[:12]:
            if m.start() < last:
                continue
            a, b = max(0, m.start() - width), min(len(t), m.end() + width)
            print("   ..." + t[a:b] + "...")
            last = b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--grep")
    a = ap.parse_args()
    ids = a.only.split(",") if a.only else None
    if a.grep:
        grep(a.grep, ids)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = lc.read_json(SRC)
    seen = set()
    for s in srcs:
        if s["id"] in seen:
            sys.exit(f"duplicate id in web_sources.json: {s['id']}")
        seen.add(s["id"])
    manifest = lc.read_json(MANIFEST) if MANIFEST.exists() else {}
    for s in srcs:
        sid, url, via = s["id"], s["url"], s.get("via", "direct")
        if ids and sid not in ids:
            continue
        m = manifest.get(sid) or {}
        if not a.refresh and not ids and m.get("status") == 200 and m.get("url") == url \
                and m.get("via") == via and (OUT / f"{sid}.txt").exists():
            continue
        rec = fetch_bd(sid, url) if via == "brightdata" else fetch_direct(sid, url)
        manifest[sid] = rec
        print(f"{rec.get('status')} {sid} {url} chars={rec.get('text_chars')} {rec.get('error', '')}",
              file=sys.stderr)
        lc.write_json(MANIFEST, manifest)
        if via != "brightdata":
            time.sleep(0.4)
    lc.write_json(MANIFEST, manifest)
    if via_bd := [s for s in srcs if s.get("via") == "brightdata"]:
        print(f"brightdata sources: {len(via_bd)}; Bright Data requests used: {lc.bd_used()}", file=sys.stderr)


if __name__ == "__main__":
    main()
