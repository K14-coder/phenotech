"""Fetch patient-organisation / registry web pages (web_sources.json) and store raw HTML + text, so
every Website quote can be string-matched against the stored page (adapted from
pipeline/community/fetch_web.py). E-mail addresses are redacted from everything saved.

Run:  python3 pipeline/families/rasopathy/fetch_web.py              # fetch pages not yet stored
      python3 pipeline/families/rasopathy/fetch_web.py --only a,b    # (re)fetch selected ids
      python3 pipeline/families/rasopathy/fetch_web.py --bd a,b      # fetch selected ids via Bright Data Web Unlocker
      python3 pipeline/families/rasopathy/fetch_web.py --grep 'regex' [--only a,b]
Out:  data/raw/families/rasopathy/web/<id>.html, <id>.txt, _manifest.json
Bright Data responses are cached under data/raw/families/rasopathy/brightdata/ and counted
(bd_usage.json, hard cap 150 requests).
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

from ras_common import HERE, RAW, ROOT, TODAY, norm, read_json, redact_emails, write_json

OUT = RAW / "web"
SRC = HERE / "web_sources.json"
BD_USAGE = RAW / "bd_usage.json"
BD_CAP = 150
BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header",
         "footer", "ul", "ol", "table", "blockquote", "figcaption"}
SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
      "Safari/537.36 rare-disease-atlas/0.1")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.meta = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        if tag == "meta":
            a = dict(attrs)
            if (a.get("name") or a.get("property") or "").lower() in ("description", "og:description", "og:title") \
                    and a.get("content"):
                self.meta.append(a["content"])
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
    body = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    body = re.sub(r"\n\s*\n+", "\n", body)
    meta = "\n".join(html.unescape(m) for m in p.meta)
    return (("[meta] " + meta + "\n") if meta else "") + body.strip()


def fetch_direct(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                                               "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", errors="replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:200], url


def fetch_bd(url):
    sys.path.insert(0, str(ROOT / "pipeline"))
    import brightdata  # noqa: E402
    brightdata.CACHE_DIR = RAW / "brightdata"     # keep this family's raw data in its own folder
    usage = read_json(BD_USAGE) if BD_USAGE.exists() else {"requests": 0, "log": []}
    cache_hit = any(x["url"] == url for x in usage["log"])
    if not cache_hit and usage["requests"] >= BD_CAP:
        raise RuntimeError("Bright Data cap reached")
    rec = brightdata.fetch(url)
    if not cache_hit:
        usage["requests"] += 1
        usage["log"].append({"kind": "unlocker", "url": url, "date": TODAY})
        write_json(BD_USAGE, usage)
    return 200, rec["html"] or "", url


def store(sid, url, status, raw, final, via):
    raw = redact_emails(raw)
    ok = status == 200 and len(raw) > 500 and not re.search(r"(Access denied|403 Forbidden|Just a moment\.\.\.)",
                                                            raw[:3000])
    (OUT / f"{sid}.html").write_text(raw)
    text = redact_emails(html_to_text(raw))
    (OUT / f"{sid}.txt").write_text(text)
    return {"id": sid, "url": url, "final_url": final, "status": 200 if ok else (status or 0), "via": via,
            "retrieved": TODAY, "bytes": len(raw), "text_chars": len(text)}


def grep(pattern, ids, width=220):
    rx = re.compile(pattern, re.I)
    for f in sorted(OUT.glob("*.txt")):
        if ids and f.stem not in ids:
            continue
        t = norm(f.read_text())
        hits = list(rx.finditer(t))
        if hits:
            print(f"--- {f.stem} ({len(hits)} hits)")
            last = -1
            for m in hits[:10]:
                if m.start() < last:
                    continue
                a, b = max(0, m.start() - width), min(len(t), m.end() + width)
                print("   …" + t[a:b] + "…")
                last = b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--bd")
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
    bd_ids = set(a.bd.split(",")) if a.bd else set()
    for s in srcs:
        sid, url = s["id"], s["url"]
        if bd_ids:
            if sid not in bd_ids:
                continue
            status, raw, final = fetch_bd(url)
            manifest[sid] = store(sid, url, status, raw, final, "brightdata")
        else:
            if ids and sid not in ids:
                continue
            if not ids and manifest.get(sid, {}).get("status") == 200:
                continue
            status, raw, final = fetch_direct(url)
            manifest[sid] = store(sid, url, status, raw if status == 200 else "", final, "direct")
        m = manifest[sid]
        print(f"{m['status']} {sid} {url} chars={m['text_chars']} via={m['via']}")
        write_json(man_path, manifest)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
