"""Fetch organisation / resource web pages listed in web_sources.json and store raw HTML + text.

Every website quote in community.json must string-match the stored text (build_community.py
checks this), so this script is the evidence store for "Website" evidence.

Usage:
  python3 pipeline/community/fetch_web.py                 # fetch any not yet stored
  python3 pipeline/community/fetch_web.py --refresh       # re-fetch everything
  python3 pipeline/community/fetch_web.py --only a,b      # fetch selected ids
  python3 pipeline/community/fetch_web.py --grep 'regex' [--only a,b]   # search stored text
E-mail addresses are redacted from everything saved.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from html.parser import HTMLParser

from common import PIPE, RAW, http, norm_ws, read_json, redact_emails, today, write_json

OUT = RAW / "web"
SRC = PIPE / "web_sources.json"
BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
         "header", "footer", "ul", "ol", "table", "blockquote", "figcaption", "span"}
SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.meta = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        if tag == "meta":
            a = dict(attrs)
            if (a.get("name") or a.get("property") or "").lower() in ("description", "og:description", "og:title") and a.get("content"):
                self.meta.append(a["content"])
        if tag in BLOCK and tag != "span":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag in BLOCK and tag != "span":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    try:
        p.feed(raw)
    except Exception:
        pass
    body = "".join(p.parts)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body)
    meta = "\n".join(html.unescape(m) for m in p.meta)
    return (("[meta] " + meta + "\n") if meta else "") + body.strip()


def fetch_one_bd(sid: str, url: str) -> dict:
    """Fetch through Bright Data Web Unlocker (pipeline/brightdata.py, cached in data/raw/brightdata/)."""
    sys.path.insert(0, str(PIPE.parent))
    import brightdata  # noqa: E402
    try:
        rec = brightdata.fetch(url)
    except Exception as e:
        return {"id": sid, "url": url, "status": None, "via": "brightdata", "error": str(e)[:200], "retrieved": today()}
    raw = redact_emails(rec["html"] or "")
    ok = len(raw) > 500 and not re.search(r"(Access denied|403 Forbidden|Just a moment\.\.\.)", raw[:3000])
    (OUT / f"{sid}.html").write_text(raw)
    text = redact_emails(html_to_text(raw))
    (OUT / f"{sid}.txt").write_text(text)
    return {"id": sid, "url": url, "final_url": url, "status": 200 if ok else 0, "via": "brightdata",
            "retrieved": rec.get("retrieved", today()), "bytes": len(raw), "text_chars": len(text)}


def fetch_one(sid: str, url: str) -> dict:
    try:
        status, body, final = http(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36 rare-disease-atlas/0.1",
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "en"}, retries=3, timeout=40)
    except Exception as e:  # network failure: record it, keep going
        return {"id": sid, "url": url, "status": None, "error": str(e)[:200], "retrieved": today()}
    raw = body.decode("utf-8", errors="replace")
    raw = redact_emails(raw)
    (OUT / f"{sid}.html").write_text(raw)
    text = redact_emails(html_to_text(raw))
    (OUT / f"{sid}.txt").write_text(text)
    return {"id": sid, "url": url, "final_url": final, "status": status, "retrieved": today(),
            "bytes": len(body), "text_chars": len(text)}


def grep(pattern: str, ids: list[str] | None, width: int = 220):
    rx = re.compile(pattern, re.I)
    for f in sorted(OUT.glob("*.txt")):
        sid = f.stem
        if ids and sid not in ids:
            continue
        t = norm_ws(f.read_text())
        hits = list(rx.finditer(t))
        if not hits:
            continue
        print(f"--- {sid} ({len(hits)} hits)")
        last = -1
        for m in hits[:12]:
            if m.start() < last:
                continue
            a, b = max(0, m.start() - width), min(len(t), m.end() + width)
            print("   …" + t[a:b] + "…")
            last = b


def main():
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
    srcs = read_json(SRC)
    man_path = OUT / "_manifest.json"
    manifest = read_json(man_path) if man_path.exists() else {}
    for s in srcs:
        sid, url = s["id"], s["url"]
        if ids and sid not in ids:
            continue
        if not a.refresh and not ids and sid in manifest and manifest[sid].get("status") == 200 \
                and manifest[sid].get("url") == url:
            continue
        rec = fetch_one_bd(sid, url) if s.get("via") == "brightdata" else fetch_one(sid, url)
        manifest[sid] = rec
        print(f"{rec.get('status')} {sid} {url} chars={rec.get('text_chars')} {rec.get('error','')}", file=sys.stderr)
        time.sleep(0.5)
    write_json(man_path, manifest)


if __name__ == "__main__":
    main()
