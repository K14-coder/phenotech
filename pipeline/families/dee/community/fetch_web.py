"""Fetch the organisation / registry pages listed in web_sources.json and store raw HTML + text.

Direct fetch first; if that fails (HTTP error, bot wall or near-empty page) the page is fetched
once through Bright Data Web Unlocker (budgeted, cached in data/raw/families/dee/community/brightdata).
Every Website quote in the fragment must string-match the stored text (verify_community.py).

Usage:
  python3 fetch_web.py                       # fetch any source not yet stored OK
  python3 fetch_web.py --only a,b [--refresh]
  python3 fetch_web.py --no-bd               # never fall back to Bright Data
  python3 fetch_web.py --grep 'regex' [--only a,b]
  python3 fetch_web.py --links 'regex' --only a   # list links in a stored page (discovery)
E-mail addresses are redacted from everything saved.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.parse
from html.parser import HTMLParser

from dee_common import BROWSER_UA, PIPE, WEB, bd_fetch, http, norm, read_json, redact_emails, today, write_json

SRC = PIPE / "web_sources.json"
BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
         "header", "footer", "ul", "ol", "table", "blockquote", "figcaption", "td", "th", "dd", "dt"}
SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
BOT_RX = re.compile(r"(Access denied|403 Forbidden|Just a moment\.\.\.|Attention Required|cf-browser-verification|"
                    r"Enable JavaScript and cookies to continue|captcha)", re.I)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.meta, self.links = [], 0, [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self.skip += 1
        if tag == "meta":
            if (a.get("name") or a.get("property") or "").lower() in ("description", "og:description", "og:title") and a.get("content"):
                self.meta.append(a["content"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    try:
        p.feed(raw)
    except Exception:  # noqa: BLE001
        pass
    body = "".join(p.parts)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body)
    meta = "\n".join(html.unescape(m) for m in p.meta)
    return (("[meta] " + meta + "\n") if meta else "") + body.strip()


def page_links(raw: str) -> list[str]:
    p = _Text()
    try:
        p.feed(raw)
    except Exception:  # noqa: BLE001
        pass
    return p.links


def _store(sid: str, raw: str) -> str:
    raw = redact_emails(raw)
    (WEB / f"{sid}.html").write_text(raw)
    text = redact_emails(html_to_text(raw))
    (WEB / f"{sid}.txt").write_text(text)
    return text


def _ok(status, raw: str, text: str) -> bool:
    return status == 200 and len(text) > 300 and not BOT_RX.search(raw[:4000] if len(text) < 3000 else "")


def fetch_one(sid: str, url: str, allow_bd: bool) -> dict:
    rec = {"id": sid, "url": url, "retrieved": today()}
    try:
        status, body, final = http(url, headers={"User-Agent": BROWSER_UA,
                                                 "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                                 "Accept-Language": "en"}, retries=2, timeout=40)
        raw = body.decode("utf-8", errors="replace")
        text = _store(sid, raw)
        rec.update({"via": "direct", "final_url": final, "status": status, "bytes": len(body), "text_chars": len(text)})
        if _ok(status, raw, text):
            rec["status"] = 200
            return rec
        rec["direct_problem"] = f"status={status} text_chars={len(text)}"
    except Exception as e:  # noqa: BLE001
        rec.update({"via": "direct", "status": None, "error": str(e)[:200]})
    if not allow_bd:
        return rec
    bd = bd_fetch(url)
    if not bd:
        return rec
    raw = bd["html"] or ""
    text = _store(sid, raw)
    ok = len(text) > 300 and not BOT_RX.search(raw[:4000] if len(text) < 3000 else "")
    rec.update({"via": "brightdata", "final_url": url, "status": 200 if ok else 0, "retrieved": bd.get("retrieved", today()),
                "bytes": len(raw), "text_chars": len(text)})
    return rec


def grep(pattern: str, ids, width: int = 200):
    rx = re.compile(pattern, re.I)
    for f in sorted(WEB.glob("*.txt")):
        if ids and f.stem not in ids:
            continue
        t = norm(f.read_text())
        hits = list(rx.finditer(t))
        if not hits:
            continue
        print(f"--- {f.stem} ({len(hits)} hits)")
        last = -1
        for m in hits[:10]:
            if m.start() < last:
                continue
            a, b = max(0, m.start() - width), min(len(t), m.end() + width)
            print("   ..." + t[a:b] + "...")
            last = b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--grep")
    ap.add_argument("--links")
    ap.add_argument("--no-bd", action="store_true")
    a = ap.parse_args()
    ids = a.only.split(",") if a.only else None
    WEB.mkdir(parents=True, exist_ok=True)
    if a.grep:
        grep(a.grep, ids)
        return
    man_path = WEB / "_manifest.json"
    manifest = read_json(man_path) if man_path.exists() else {}
    if a.links:
        rx = re.compile(a.links, re.I)
        for sid in ids or []:
            base = manifest.get(sid, {}).get("final_url") or manifest.get(sid, {}).get("url")
            raw = (WEB / f"{sid}.html").read_text() if (WEB / f"{sid}.html").exists() else ""
            seen = set()
            for l in page_links(raw):
                u = urllib.parse.urljoin(base or "", l)
                if rx.search(u) and u not in seen:
                    seen.add(u)
                    print(sid, u)
        return
    for s in read_json(SRC):
        sid, url = s["id"], s["url"]
        if ids and sid not in ids:
            continue
        m = manifest.get(sid, {})
        if not a.refresh and m.get("url") == url and (m.get("status") == 200 or (m.get("tried_bd") and a.no_bd)):
            continue
        if not a.refresh and m.get("url") == url and m.get("gave_up"):
            continue
        allow_bd = (not a.no_bd) and s.get("bd", True)
        rec = fetch_one(sid, url, allow_bd)
        if rec.get("status") != 200:
            rec["gave_up"] = True
        rec["tried_bd"] = allow_bd
        manifest[sid] = rec
        print(f"{rec.get('status')} {rec.get('via')} {sid} {url} chars={rec.get('text_chars')} {rec.get('error','')}{rec.get('direct_problem','')}",
              file=sys.stderr)
        write_json(man_path, manifest)
        time.sleep(0.3)
    write_json(man_path, manifest)


if __name__ == "__main__":
    main()
