"""Bright Data client: Google results via the SERP API and blocked pages via Web Unlocker.

Reads BRIGHTDATA_API_TOKEN, BRIGHTDATA_SERP_ZONE and BRIGHTDATA_UNLOCKER_ZONE from the
environment, falling back to .env.local at the project root. Every response is cached under
data/raw/brightdata/, so re-running the pipeline doesn't spend credits again.

Usage:
    python pipeline/brightdata.py check
    python pipeline/brightdata.py search "VAMP2 patient foundation"
    python pipeline/brightdata.py fetch https://example.org
"""

import datetime
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "raw" / "brightdata"
API_URL = "https://api.brightdata.com/request"


def _load_env():
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def _config():
    _load_env()
    token = os.environ.get("BRIGHTDATA_API_TOKEN")
    if not token:
        raise RuntimeError("BRIGHTDATA_API_TOKEN is not set (add it to .env.local)")
    return {
        "token": token,
        "serp_zone": os.environ.get("BRIGHTDATA_SERP_ZONE", "serp_api1"),
        "unlocker_zone": os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker1"),
    }


def _request(zone, url, kind, use_cache=True):
    cache_file = CACHE_DIR / kind / (hashlib.sha256(f"{zone}|{url}".encode()).hexdigest()[:24] + ".json")
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text())

    cfg = _config()
    body = json.dumps({"zone": zone, "url": url, "format": "raw"}).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['token']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Bright Data {zone} returned HTTP {err.code}: {detail}") from None

    record = {
        "url": url,
        "zone": zone,
        "retrieved": datetime.date.today().isoformat(),
        "body": text,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(record, ensure_ascii=False))
    return record


def search(query, num=10, use_cache=True):
    """Google results for `query` as a list of {rank, title, link, description}."""
    cfg = _config()
    params = urllib.parse.urlencode({"q": query, "num": num, "hl": "en", "gl": "us", "brd_json": 1})
    record = _request(cfg["serp_zone"], f"https://www.google.com/search?{params}", "serp", use_cache)
    try:
        parsed = json.loads(record["body"])
    except json.JSONDecodeError:
        raise RuntimeError("SERP response was not JSON; check that the zone is a SERP API zone") from None
    return [
        {
            "rank": item.get("rank"),
            "title": item.get("title"),
            "link": item.get("link"),
            "description": item.get("description"),
        }
        for item in parsed.get("organic", [])
    ]


def fetch(url, use_cache=True):
    """Page content for `url` through Web Unlocker, with the retrieval date for citations."""
    cfg = _config()
    record = _request(cfg["unlocker_zone"], url, "unlocker", use_cache)
    return {"url": url, "retrieved": record["retrieved"], "html": record["body"]}


def _check():
    cfg = _config()
    test = _request(
        cfg["unlocker_zone"], "https://geo.brdtest.com/welcome.txt?product=unlocker&method=api", "unlocker", False
    )
    print(f"Web Unlocker ({cfg['unlocker_zone']}): OK, {len(test['body'])} chars")
    results = search("STXBP1 foundation", num=5, use_cache=False)
    print(f"SERP API ({cfg['serp_zone']}): OK, {len(results)} organic results")
    for r in results:
        print(f"  {r['rank']}. {r['title']} - {r['link']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        _check()
    elif cmd == "search":
        print(json.dumps(search(" ".join(sys.argv[2:])), indent=2))
    elif cmd == "fetch":
        page = fetch(sys.argv[2])
        print(page["html"][:2000])
    else:
        sys.exit(__doc__)
