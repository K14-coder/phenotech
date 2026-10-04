"""Extract organisation-published contact details (general email / phone) for patient
organisations, registries and foundations.

Scope: orgs serving the 45 deep diseases (graph patient_org + asset nodes, and scale orgs linked
to those diseases) plus the top 300 scale orgs by disease coverage.

Sources, in order:
 1. pages already stored: data/raw/community/web, data/raw/families/*/web,
    data/raw/families/dee/community/web, Bright Data unlocker caches, data/raw/scale/pages.
 2. for orgs still without a contact: ONE contact page per org (same host, found via a link whose
    text or href says "contact" on the stored homepage; if the stored homepage is text-only the
    homepage is re-fetched once to read its links). Plain fetch first; Bright Data Web Unlocker
    fallback, capped at 150 requests. All fetches cached in data/raw/contacts/web/.

Output: data/raw/contacts/orgs_extracted.json (validate.py + build.py turn it into derived data).
Run: python3 pipeline/contacts/extract_orgs.py [--no-fetch]
"""

import concurrent.futures as cf
import datetime
import glob
import hashlib
import html as htmllib
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
RAW = ROOT / "data" / "raw" / "contacts"
WEB = RAW / "web"
BD_DIR = RAW / "brightdata"
OUT = RAW / "orgs_extracted.json"
BD_BUDGET = 150
TODAY = datetime.date.today().isoformat()

DIRECTORY_HOSTS = {"globalgenes.org", "rarediseases.org", "eurordis.org", "geneticalliance.org.uk",
                   "clinicaltrials.gov", "facebook.com", "instagram.com", "twitter.com", "x.com",
                   "linkedin.com", "youtube.com", "orpha.net", "ncbi.nlm.nih.gov"}


def host_of(url):
    try:
        h = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""
    h = h.lower()
    return h[4:] if h.startswith("www.") else h


# ---------------------------------------------------------------- page index
def visible_text(raw_html):
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", raw_html)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|footer|section|address|span|a)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = htmllib.unescape(t)
    t = re.sub(r"[ \t\r\f\v ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def load_pages():
    pages = []  # {url, retrieved, html|None, text}
    for mf in [ROOT / "data/raw/community/web/_manifest.json",
               *map(pathlib.Path, glob.glob(str(ROOT / "data/raw/families/*/web/_manifest.json"))),
               ROOT / "data/raw/families/dee/community/web/_manifest.json"]:
        if not mf.exists():
            continue
        d = mf.parent
        for key, m in json.loads(mf.read_text()).items():
            hf = d / f"{key}.html"
            if not hf.exists() or str(m.get("status")) not in ("200", "None"):
                continue
            h = hf.read_text(errors="replace")
            pages.append({"url": m.get("final_url") or m["url"], "retrieved": m.get("retrieved"),
                          "html": h, "text": None})
    for f in glob.glob(str(ROOT / "data/raw/**/brightdata/unlocker/*.json"), recursive=True):
        if "/contacts/" in f:
            continue
        r = json.loads(pathlib.Path(f).read_text())
        if r.get("body") and "<" in r["body"][:2000]:
            pages.append({"url": r["url"], "retrieved": r.get("retrieved"), "html": r["body"], "text": None})
    for f in glob.glob(str(ROOT / "data/raw/scale/pages/*.json")):
        r = json.loads(pathlib.Path(f).read_text())
        if str(r.get("status")) == "200" and r.get("text"):
            pages.append({"url": r.get("final_url") or r["url"], "retrieved": r.get("retrieved"),
                          "html": None, "text": r["text"]})
    for f in glob.glob(str(WEB / "*.json")):  # our own fetches
        r = json.loads(pathlib.Path(f).read_text())
        if r.get("html"):
            pages.append({"url": r["final_url"], "retrieved": r["retrieved"], "html": r["html"], "text": None,
                          "fetched_here": True})
    for p in pages:
        if p["text"] is None:
            p["text"] = visible_text(p["html"])
        p["host"] = host_of(p["url"])
    return pages


# ---------------------------------------------------------------- extraction
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}(?![\w-])")
PHONE_KW = re.compile(r"(?i)\b(phone|telephone|tel|call|helpline|hotline|freephone|toll[- ]free|fax|ph|mobile|cell)\b")
PHONE_RE = re.compile(r"(?<![\w/.-])(\+?\(?\d{1,4}\)?[\s.\-]?(?:\(?\d{1,5}\)?[\s.\-]?){2,5}\d{2,5})(?![\w/-])")
BAD_EMAIL = re.compile(r"(?i)(\.(png|jpe?g|gif|svg|webp|css|js)$|example\.(com|org)|sentry|wixpress|domain\.com|"
                       r"yourdomain|email\.com$|@2x|@3x|u00|godaddy|squarespace|mysite|test@|name@|user@|"
                       r"username@|you@|your@|john@|jane@|firstname|lastname)")


def snippet(text, start, end, width=110):
    a, b = max(0, start - width), min(len(text), end + width)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _cf_decode(hexs):
    try:
        key = int(hexs[:2], 16)
        return "".join(chr(int(hexs[i:i + 2], 16) ^ key) for i in range(2, len(hexs), 2))
    except ValueError:
        return ""


def decode_cfemail(raw):
    """Cloudflare email obfuscation: the address is published, just XOR-encoded in the HTML."""
    raw = re.sub(r"(?is)<(span|a)[^>]*data-cfemail=[\"']([0-9a-f]+)[\"'][^>]*>.*?</\1>",
                 lambda m: _cf_decode(m.group(2)), raw)
    return re.sub(r"(?i)/cdn-cgi/l/email-protection#([0-9a-f]+)", lambda m: "mailto:" + _cf_decode(m.group(1)), raw)


def extract(page):
    """Return list of {kind, value, snippet, before, how}."""
    text, raw = page["text"], page["html"]
    if raw and ("cfemail" in raw or "email-protection" in raw):
        raw = decode_cfemail(raw)
        text = visible_text(raw)
    found = []
    if raw:
        for m in re.finditer(r"(?is)<a\b[^>]*href\s*=\s*[\"']\s*(mailto|tel):([^\"'?]+)[^\"']*[\"'][^>]*>(.*?)</a>", raw):
            kind = "email" if m.group(1).lower() == "mailto" else "phone"
            val = urllib.parse.unquote(htmllib.unescape(m.group(2))).strip()
            label = visible_text(m.group(3))[:80]
            pos = text.find(label) if label else -1
            if kind == "email":
                pos2 = text.lower().find(val.lower())
                pos = pos2 if pos2 >= 0 else pos
            if pos >= 0 and label:
                snip = snippet(text, pos, pos + len(label))
            else:
                snip = re.sub(r"\s+", " ", m.group(0))[:240]
            before = text[max(0, pos - 150):pos] if pos >= 0 else visible_text(m.group(0))
            found.append({"kind": kind, "value": val, "snippet": snip, "before": before,
                          "how": m.group(1).lower() + "_link"})
    for m in EMAIL_RE.finditer(text):
        found.append({"kind": "email", "value": m.group(0), "snippet": snippet(text, m.start(), m.end()),
                      "before": text[max(0, m.start() - 150):m.start()], "how": "visible_text"})
    for line_m in re.finditer(r"[^\n]+", text):
        line = line_m.group(0)
        if len(line) > 400 or not PHONE_KW.search(line):
            continue
        for m in PHONE_RE.finditer(line):
            digits = re.sub(r"\D", "", m.group(1))
            if not 7 <= len(digits) <= 15:
                continue
            if re.search(r"(?i)(charity|company|registered|reg\.?|ein|tax|no\.)\s*(number|no\.?|#)?\s*:?\s*$",
                         line[:m.start()][-40:]):
                continue
            if re.fullmatch(r"(19|20)\d{2}[\s.\-]?\d{1,2}[\s.\-]?\d{1,2}", m.group(1).strip()):
                continue
            off = line_m.start()
            found.append({"kind": "phone", "value": m.group(1).strip(),
                          "snippet": snippet(text, off + m.start(), off + m.end()),
                          "before": text[max(0, off + m.start() - 150):off + m.start()], "how": "visible_text"})
    return found


CC = {"uk": "44", "gb": "44", "de": "49", "fr": "33", "nl": "31", "it": "39", "es": "34", "au": "61",
      "ca": "1", "us": "1", "ie": "353", "be": "32", "ch": "41", "se": "46", "dk": "45", "no": "47",
      "nz": "64", "at": "43", "pt": "351", "fi": "358", "pl": "48", "il": "972", "in": "91", "za": "27",
      "br": "55", "jp": "81", "mx": "52", "ar": "54", "gr": "30", "cz": "420", "hu": "36"}


NAME_CC = [(r"(?i)asociaci|fundaci[oó]n|espa[nñ]a", "34"), (r"(?i)associazione|onlus|odv|italia", "39"),
           (r"(?i)\be\.\s?v\.|verein|deutschland|bundesverband", "49"), (r"(?i)vereniging|nederland", "31"),
           (r"(?i)fundacja|stowarzyszenie|polska|poland", "48"), (r"(?i)france|fran[cç]aise", "33"),
           (r"(?i)\buk\b|united kingdom|british", "44"), (r"(?i)\b(les|des|du|maladies|vaincre|contre)\b", "33")]


def country_code(org_country, host, name=""):
    if org_country and org_country.lower() in CC:
        return CC[org_country.lower()]
    tld = host.rsplit(".", 1)[-1]
    if tld in CC:
        return CC[tld]
    for pat, cc in NAME_CC:
        if re.search(pat, name or ""):
            return cc
    return None


def _strip_trunk(e):
    # "+44 (0) 1453..." / "+610383..." -> drop the national trunk 0 (Italy keeps it)
    if not e.startswith("+39"):
        for cc in sorted(set(CC.values()) | {"380", "385", "40", "357", "421", "54"}, key=len, reverse=True):
            if e.startswith("+" + cc + "0"):
                return "+" + cc + e[len(cc) + 2:]
    return e


def to_e164(raw, cc):
    s = raw.strip().replace("(0)", "")
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        return _strip_trunk("+" + digits) if 8 <= len(digits) <= 15 else None
    if s.startswith("00") and len(digits) > 10:
        return _strip_trunk("+" + digits[2:])
    nanp = re.fullmatch(r"(1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-]\d{3}[\s.\-]\d{4}", s)
    if cc is None and nanp:
        cc = "1"  # printed in North American format on a site with no other country signal
    if cc is None and re.fullmatch(r"0[1-37]\d{9}", digits):
        cc = "44"  # 11-digit 0-prefixed national format is British
    if cc == "34" and len(digits) == 9 and digits[0] in "6789":
        return "+34" + digits
    if cc == "39" and 6 <= len(digits) <= 11 and digits[0] in "03":
        return "+39" + digits
    if cc == "1":
        if len(digits) == 10 and digits[0] in "23456789":
            return "+1" + digits
        if len(digits) == 11 and digits[0] == "1":
            return "+" + digits
        return None
    if cc and digits.startswith("0") and 8 <= len(digits) <= 12:
        return "+" + cc + digits[1:]
    if cc and digits.startswith(cc) and len(digits) >= 10:
        return _strip_trunk("+" + digits)
    return None


# ---------------------------------------------------------------- org scope
def org_targets():
    g = json.loads((ROOT / "data/graph.json").read_text())
    deep_ids = set()
    for n in g["nodes"]:
        if n["type"] == "disease":
            x = n.get("xrefs") or {}
            deep_ids.update(x.get("MONDO", []) if isinstance(x.get("MONDO"), list) else [x.get("MONDO")])
            for p in ("OMIM", "ORPHA"):
                v = x.get(p) or []
                deep_ids.update(f"{p}:{i}" for i in (v if isinstance(v, list) else [v]))
    deep_ids.discard(None)
    targets = {}
    for n in g["nodes"]:
        if n["type"] in ("patient_org", "asset") and n["attrs"].get("url"):
            if n["type"] == "asset" and n["attrs"].get("kind") in ("animal_model", "outcome_measure", "funding_program"):
                continue
            url = n["attrs"]["url"] if host_of(n["attrs"]["url"]) not in DIRECTORY_HOSTS else None
            targets[n["id"]] = {"id": n["id"], "name": n["label"], "layer": "graph", "node_type": n["type"],
                                "url": url, "country": n["attrs"].get("country"),
                                "scope": "deep"}
    so = json.loads((ROOT / "data/derived/scale/orgs.json").read_text())["orgs"]
    ranked = sorted(so, key=lambda o: -len(o.get("diseases", [])))
    top = {o["id"] for o in ranked[:300]}
    for o in so:
        deep = any(d.get("id") in deep_ids or d.get("mondo") in deep_ids for d in o.get("diseases", []))
        if not (deep or o["id"] in top):
            continue
        site = o.get("website") or o.get("url")
        if not site or host_of(site) in DIRECTORY_HOSTS:
            site = None
        key = o["id"]
        if key in targets:  # reused graph id
            targets[key]["scale_diseases"] = len(o.get("diseases", []))
            continue
        targets[key] = {"id": key, "name": o["name"], "layer": "scale", "node_type": "patient_org",
                        "url": site, "country": o.get("country"), "scale_diseases": len(o.get("diseases", [])),
                        "scope": "deep" if deep else "top300"}
    return targets


# ---------------------------------------------------------------- fetching
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def cache_path(url):
    return WEB / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def plain_fetch(url):
    cp = cache_path(url)
    if cp.exists():
        return json.loads(cp.read_text())
    rec = {"url": url, "retrieved": TODAY, "via": "direct"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=20) as r:
            rec["final_url"] = r.geturl()
            rec["status"] = r.status
            rec["html"] = r.read(3_000_000).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)[:200]
    cp.write_text(json.dumps(rec, ensure_ascii=False))
    return rec


BD_USED = {"n": 0}


def bd_fetch(url):
    """Bright Data Web Unlocker fallback; token read via pipeline/brightdata.py's loader, never printed."""
    cp = cache_path("bd|" + url)
    if cp.exists():
        return json.loads(cp.read_text())
    if BD_USED["n"] >= BD_BUDGET:
        return None
    BD_USED["n"] += 1
    import brightdata  # noqa: PLC0415
    cfg = brightdata._config()
    rec = {"url": url, "retrieved": TODAY, "via": "brightdata"}
    try:
        body = json.dumps({"zone": cfg["unlocker_zone"], "url": url, "format": "raw"}).encode()
        req = urllib.request.Request(brightdata.API_URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {cfg['token']}"})
        with urllib.request.urlopen(req, timeout=90) as r:
            rec["html"] = r.read().decode("utf-8", errors="replace")
            rec["final_url"] = url
            rec["status"] = 200
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)[:200].replace(cfg["token"], "***")
    cp.write_text(json.dumps(rec, ensure_ascii=False))
    with open(RAW / "brightdata_usage.jsonl", "a") as f:
        f.write(json.dumps({"url": url, "ok": "html" in rec, "date": TODAY}) + "\n")
    return rec


def good(rec):
    return rec and rec.get("html") and len(rec["html"]) > 800 and str(rec.get("status")) == "200"


def find_contact_link(home_html, base, host):
    best = None
    for m in re.finditer(r"(?is)<a\b[^>]*href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", home_html):
        href, label = m.group(1).strip(), visible_text(m.group(2)).lower()
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        absu = urllib.parse.urljoin(base, href)
        if host_of(absu) != host:
            continue
        path = urllib.parse.urlsplit(absu).path.lower()
        score = 0
        if re.search(r"contact", label):
            score += 2
        if re.search(r"contact", path):
            score += 2
        if re.search(r"(?i)form|contact-?form|sales|press|media", path):
            score -= 1
        if score >= 2 and (best is None or score > best[0]):
            best = (score, absu)
    return best[1] if best else None


def fetch_contact_page(org, pages_by_host):
    host = host_of(org["url"])
    home = next((p for p in pages_by_host.get(host, []) if p["html"]), None)
    log = {"org": org["id"], "host": host}
    if home is None:
        r = plain_fetch(org["url"])
        if not good(r):
            log["result"] = "homepage_refetch_failed"
            return log, None
        home = {"url": r.get("final_url") or org["url"], "html": r["html"]}
        log["homepage_refetched"] = True
        host = host_of(home["url"]) or host
    link = find_contact_link(home["html"], home["url"], host)
    if not link:
        log["result"] = "no_contact_link"
        return log, None
    log["contact_url"] = link
    r = plain_fetch(link)
    if not good(r):
        log["plain_error"] = r.get("error") or r.get("status")
        r = bd_fetch(link)
        if not good(r):
            log["result"] = "fetch_failed"
            return log, None
        log["via"] = "brightdata"
    else:
        log["via"] = "direct"
    log["result"] = "ok"
    return log, {"url": r.get("final_url") or link, "retrieved": r["retrieved"], "html": r["html"],
                 "text": visible_text(r["html"]), "host": host_of(r.get("final_url") or link),
                 "fetched_here": True}


# ---------------------------------------------------------------- main
def collect(org, pages_by_host):
    host = host_of(org["url"]) if org.get("url") else ""
    hits = {}
    for p in pages_by_host.get(host, []):
        for f in extract(p):
            key = (f["kind"], f["value"].lower() if f["kind"] == "email" else re.sub(r"\D", "", f["value"]))
            ev = {**f, "source_url": p["url"], "retrieved": p["retrieved"] or TODAY,
                  "contact_page": bool(re.search(r"(?i)contact", p["url"]))}
            if key not in hits or (ev["contact_page"] and not hits[key]["contact_page"]):
                hits[key] = ev
    return list(hits.values())


def main():
    WEB.mkdir(parents=True, exist_ok=True)
    pages = load_pages()
    pages_by_host = {}
    for p in pages:
        pages_by_host.setdefault(p["host"], []).append(p)
    targets = org_targets()
    print("stored pages:", len(pages), "targets:", len(targets),
          "with website:", sum(1 for t in targets.values() if t.get("url")))

    results = {k: collect(t, pages_by_host) for k, t in targets.items() if t.get("url")}
    import validate  # noqa: PLC0415  (same dir)
    def usable(ev_list, org):
        kept, _ = validate.filter_org_evidence(ev_list, org)
        return kept
    need = [targets[k] for k, ev in results.items() if not usable(ev, targets[k])]
    fetch_log = []
    if "--no-fetch" not in sys.argv:
        print("orgs needing a contact page:", len(need))
        # one org per host
        seen, uniq = set(), []
        for o in need:
            h = host_of(o["url"])
            if h and h not in seen and h not in DIRECTORY_HOSTS:
                seen.add(h)
                uniq.append(o)
        with cf.ThreadPoolExecutor(8) as ex:
            for log, page in ex.map(lambda o: fetch_contact_page(o, pages_by_host), uniq):
                fetch_log.append(log)
                if page:
                    pages_by_host.setdefault(page["host"], []).append(page)
                    pages_by_host.setdefault(log["host"], []).append(page) if page["host"] != log["host"] else None
        for o in need:
            results[o["id"]] = collect(o, pages_by_host)
    out = {"meta": {"built": TODAY, "stored_pages": len(pages), "targets": len(targets),
                    "brightdata_requests": BD_USED["n"], "fetch_log": fetch_log},
           "orgs": {k: {**t, "evidence": results.get(k, [])} for k, t in targets.items()}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("brightdata used:", BD_USED["n"], "fetch results:",
          {r: sum(1 for l in fetch_log if l.get("result") == r) for r in {l.get("result") for l in fetch_log}})


if __name__ == "__main__":
    main()
