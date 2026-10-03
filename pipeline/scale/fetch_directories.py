"""Fetch the four patient-organisation directories (raw pages cached under data/raw/scale/).

  Global Genes - Global Advocacy Alliance (formerly RARE Foundation Alliance)
      page:  https://globalgenes.org/about-us/global-advocacy-alliance/global-advocacy-alliance-members/
      data:  the page renders https://globalgenes.org/wp-json/gg/v1/gaa?page=N (30 members/page) -> Bright Data
  NORD - Organizational Database (ODB, the 'Find a Patient Organization' directory; members flagged "NORD Member")
      https://rarediseases.org/organizations/page/N/  -> Bright Data (Cloudflare blocks direct fetches)
  EURORDIS - member list
      https://www.eurordis.org/who-we-are/our-members/ renders results from a POST to admin-ajax.php
      (action=members_search, no filters = all members). Direct, one request.
  Genetic Alliance UK - A-Z directory of member organisations (one page, direct)

Usage: python3 fetch_directories.py [gg|nord|eurordis|gauk ...]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

from common import BROWSER_UA, RAW, BudgetExceeded, _ctx, bd_fetch, get_page, today, write_json

D = RAW / "directories"
GG_PAGE = "https://globalgenes.org/about-us/global-advocacy-alliance/global-advocacy-alliance-members/"
GG_API = "https://globalgenes.org/wp-json/gg/v1/gaa"
NORD = "https://rarediseases.org/organizations/"
EURORDIS_PAGE = "https://www.eurordis.org/who-we-are/our-members/"
GAUK = "https://geneticalliance.org.uk/membership/a-z-members-directory/"


def fetch_gg(max_pages=80):
    seen, pages = set(), 0
    for n in range(1, max_pages + 1):
        url = GG_API if n == 1 else f"{GG_API}?page={n}"
        out = D / "globalgenes" / f"page_{n:03d}.json"
        if out.exists():
            recs = json.loads(out.read_text())["records"]
        else:
            r = bd_fetch(url)
            try:
                recs = json.loads(r["html"])
            except json.JSONDecodeError:
                print(f"  gg page {n}: not JSON, stopping")
                break
            write_json(out, {"url": url, "page_url": GG_PAGE, "retrieved": r["retrieved"], "records": recs})
        ids = {x["id"] for x in recs}
        if not recs or ids <= seen:
            break
        seen |= ids
        pages += 1
    print(f"Global Genes: {pages} pages, {len(seen)} members")


def fetch_nord(last_page=None):
    first = get_page(NORD, prefer_bd=True)
    import re
    if last_page is None:
        from common import get_html
        h = get_html(NORD) or ""
        nums = [int(x) for x in re.findall(r"organizations/page/(\d+)", h)]
        last_page = max(nums) if nums else 1
    ok = 1
    for n in range(2, last_page + 1):
        rec = get_page(f"{NORD}page/{n}/", prefer_bd=True)
        ok += bool(rec and rec.get("text"))
    print(f"NORD ODB: {ok}/{last_page} listing pages")


def fetch_eurordis():
    out = D / "eurordis_members.json"
    if out.exists():
        print("EURORDIS: cached")
        return
    page = get_page(EURORDIS_PAGE)  # the page the list is rendered on (kept as context)
    data = urllib.parse.urlencode({"action": "members_search", "country": "any", "diseases": "", "keyword": "",
                                   "keyword_disease": "", "kind": ""}).encode()
    req = urllib.request.Request("https://www.eurordis.org/wp-admin/admin-ajax.php", data=data, headers={
        "User-Agent": BROWSER_UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest", "Referer": EURORDIS_PAGE})
    with urllib.request.urlopen(req, timeout=90, context=_ctx()) as r:
        html = r.read().decode("utf-8", "replace")
    write_json(out, {"page_url": EURORDIS_PAGE, "endpoint": "https://www.eurordis.org/wp-admin/admin-ajax.php",
                     "post": {"action": "members_search"}, "retrieved": today(), "html": html})
    print(f"EURORDIS: {html.count('<li>')} members, page text {len(page.get('text', ''))} chars")


def fetch_gauk():
    rec = get_page(GAUK)
    print(f"Genetic Alliance UK: {rec['via']} {len(rec.get('text', ''))} chars")


def main():
    which = sys.argv[1:] or ["eurordis", "gauk", "gg", "nord"]
    try:
        for w in which:
            {"gg": fetch_gg, "nord": fetch_nord, "eurordis": fetch_eurordis, "gauk": fetch_gauk}[w]()
    except BudgetExceeded as e:
        print("STOP:", e)


if __name__ == "__main__":
    main()
