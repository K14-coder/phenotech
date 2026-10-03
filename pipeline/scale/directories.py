"""Parse the cached directory pages into flat records and match each record's stated disease focus
to the monogenic universe.

Record: {source, name, website, country, focus, quote, evidence_url, record_url}
  quote = verbatim text from the stored directory page/record (whitespace-normalised, e-mails redacted)

Matching (rule names are written into every evidence item):
  dir_disease_field_name   EURORDIS 'Disease:' / NORD 'Related Rare Diseases:' entry equals (token-normalised)
                           a disease name or synonym in the universe (whole entry, not a substring)
  dir_text_name            Global Genes mission text or any directory's org name contains a disease
                           name/synonym as a whole phrase (same name index and exclusions as trials)
  dir_text_gene            a causal gene symbol appears case-sensitively as a whole token in the org name or
                           mission text (same symbol stoplist as trials); credited to every disease of that gene
"""
from __future__ import annotations

import html as _h
import json
import re
from pathlib import Path

from common import OUT, RAW, get_html, get_page, html_to_text, norm_text, norm_ws, read_json

D = RAW / "directories"
GG_PAGE = "https://globalgenes.org/about-us/global-advocacy-alliance/global-advocacy-alliance-members/"
NORD = "https://rarediseases.org/organizations/"
EURORDIS_PAGE = "https://www.eurordis.org/who-we-are/our-members/"
GAUK = "https://geneticalliance.org.uk/membership/a-z-members-directory/"


def _clean(s):
    return norm_ws(_h.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def gg_records():
    out, seen = [], set()
    for p in sorted((D / "globalgenes").glob("page_*.json")):
        page = json.loads(p.read_text())
        for r in page["records"]:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            name = _clean(r.get("title"))
            if not name or re.fullmatch(r"[0-9a-zA-Z]{15,18}", name):  # CRM ids leaked as titles
                continue
            content = _clean(r.get("content"))
            if content.lower() in ("na", "description", "n/a"):
                content = ""
            out.append({"source": "globalgenes", "name": name, "website": (r.get("website") or "").strip() or None,
                        "country": None, "focus": content, "quote": content or name,
                        "evidence_url": GG_PAGE, "record_url": page["url"],
                        "profile_url": "https://globalgenes.org" + r["href"] if r.get("href") else None})
    return out


def eurordis_records():
    rec = json.loads((D / "eurordis_members.json").read_text())
    out = []
    for li in re.findall(r"<li>(.*?)</li>", rec["html"], re.S):
        m = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', li, re.S)
        if not m:
            continue
        name = _clean(m.group(2))
        country = re.search(r"<strong>Country:</strong>\s*(.*?)<br", li, re.S)
        disease = re.search(r"<strong>Disease:</strong>\s*(.*?)$", li, re.S)
        focus = _clean(disease.group(1)) if disease else ""
        out.append({"source": "eurordis", "name": name, "website": m.group(1).strip() or None,
                    "country": _clean(country.group(1)) if country else None,
                    "focus": focus, "focus_list": [x.strip() for x in focus.split(",") if x.strip()],
                    "quote": _clean(li), "evidence_url": EURORDIS_PAGE, "record_url": rec["endpoint"]})
    return out


def nord_records():
    out = []
    pages = [NORD] + [f"{NORD}page/{n}/" for n in range(2, 60)]
    for u in pages:
        h = get_html(u)
        if not h:
            continue
        for block in re.split(r'<div class="single-rd-resource">', h)[1:]:
            m = re.search(r'<h5[^>]*>\s*<a href="([^"]+)">(.*?)</a>', block, re.S)
            if not m:
                continue
            name = _clean(m.group(2))
            rel = re.search(r"<span>Related Rare Diseases:</span>(.*?)</span>", block, re.S)
            related = [_clean(x) for x in re.findall(r"<a[^>]*>(.*?)</a>", rel.group(1), re.S)] if rel else []
            quote = ("Related Rare Diseases: " + " , ".join(related)) if related else name
            out.append({"source": "nord", "name": name, "website": None, "country": None,
                        "focus": " , ".join(related), "focus_list": related,
                        "nord_member": "NORD Member" in block[:3000],
                        "quote": norm_ws(quote), "evidence_url": u, "profile_url": m.group(1),
                        "record_url": u})
    return out


def gauk_records():
    h = get_html(GAUK) or ""
    body = h[h.find("This is an alphabetical list"):]
    out = []
    for href, txt in re.findall(r'<li><a href="([^"]+)"[^>]*>(.*?)</a></li>', body, re.S):
        name = _clean(txt)
        if not name or "geneticalliance.org.uk" in href:
            continue
        out.append({"source": "geneticalliance_uk", "name": name, "website": href.strip(), "country": "United Kingdom",
                    "focus": name, "quote": name, "evidence_url": GAUK, "record_url": GAUK})
    return out


def all_records():
    recs = []
    for fn in (gg_records, eurordis_records, nord_records, gauk_records):
        try:
            recs += fn()
        except FileNotFoundError:
            pass
    return recs


def snippet(text: str, term_norm: str, width: int = 220) -> str | None:
    """Return a verbatim window of `text` around the first place whose normalised form contains term_norm."""
    sents = re.split(r"(?<=[.!?;])\s+", text)
    for s in sents:
        if f" {term_norm} " in f" {norm_text(s)} ":
            return s if len(s) <= width else s[:width].rsplit(" ", 1)[0] + " ..."
    return None


if __name__ == "__main__":
    from collections import Counter
    r = all_records()
    print(Counter(x["source"] for x in r))
    for src in ("globalgenes", "eurordis", "nord", "geneticalliance_uk"):
        ex = [x for x in r if x["source"] == src][:2]
        for x in ex:
            print(json.dumps(x, ensure_ascii=False)[:400])
