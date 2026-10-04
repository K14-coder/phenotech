"""Assemble data/derived/contacts/{orgs,trials}.json (+ exclusions.json, README.md) from the
extracted raw data, running the personal-data validator on everything.

Run after fetch_trials.py and extract_orgs.py:
    python3 pipeline/contacts/build.py
"""

import collections
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import validate  # noqa: E402
from extract_orgs import country_code, host_of, to_e164  # noqa: E402

ROOT = HERE.parents[1]
RAW = ROOT / "data" / "raw" / "contacts"
OUT = ROOT / "data" / "derived" / "contacts"
TODAY = datetime.date.today().isoformat()

COUNTRY_TO_CC = {"United States": "1", "Canada": "1", "United Kingdom": "44", "France": "33", "Germany": "49",
                 "Italy": "39", "Spain": "34", "Netherlands": "31", "Belgium": "32", "Australia": "61",
                 "Switzerland": "41", "Sweden": "46", "Denmark": "45", "Norway": "47", "Ireland": "353",
                 "Austria": "43", "Israel": "972", "Japan": "81", "China": "86", "Brazil": "55",
                 "Poland": "48", "Portugal": "351", "Finland": "358", "Czechia": "420", "India": "91",
                 "Korea, Republic of": "82", "Taiwan": "886", "Turkey": "90", "Türkiye": "90", "Mexico": "52",
                 "Argentina": "54", "Greece": "30", "Hungary": "36", "Egypt": "20", "New Zealand": "64"}


def mask(v):
    if "@" in v:
        local, dom = v.split("@", 1)
        return local[:1] + "***@" + dom
    d = re.sub(r"\D", "", v)
    return d[:4] + "***" + d[-2:] if len(d) > 6 else "***"


def build_orgs():
    raw = json.loads((RAW / "orgs_extracted.json").read_text())
    orgs, excluded = {}, []
    for oid, o in raw["orgs"].items():
        host = host_of(o.get("url") or "")
        cc = country_code(o.get("country"), host, o.get("name"))
        ev = []
        for e in o.get("evidence", []):
            e = dict(e)
            if e["kind"] == "phone":
                e["e164"] = to_e164(e["value"], cc)
            ev.append(e)
        kept, removed = validate.filter_org_evidence(ev, o)
        for r in removed:
            excluded.append({"org": oid, "kind": r["kind"], "value_masked": mask(r["value"]), "reason": r["reason"],
                             "source_url": r["source_url"]})
        if not kept:
            continue
        emails, phones, eev, pev, seen = [], [], [], [], set()
        for e in kept:
            if e["kind"] == "email":
                v = e["value"].lower()
                if v in seen:
                    continue
                seen.add(v)
                emails.append(v)
                eev.append({"value": v, "source_url": e["source_url"], "snippet": e["snippet"], "how": e["how"],
                            "retrieved": e["retrieved"]})
            else:
                key = (e.get("e164") or re.sub(r"\D", "", e["value"]))[-9:]
                if key in seen:
                    continue
                seen.add(key)
                phones.append({"number": e["value"], "e164": e.get("e164")})
                pev.append({"value": e["value"], "e164": e.get("e164"), "source_url": e["source_url"],
                            "before": e.get("before", ""),
                            "snippet": e["snippet"], "how": e["how"], "retrieved": e["retrieved"]})
        if len(pev) > 3:
            # a page listing many numbers is usually a directory of other people's / sites' lines:
            # keep only those labelled as the organisation's own line
            pev = [x for x in pev if validate.ORG_LINE.search((x.get("before") or "")[-50:]) or
                   validate.STRONG_CTX.search((x.get("before") or "")[-50:])]
            keepn = {x["value"] for x in pev}
            for x in phones:
                if x["number"] not in keepn:
                    excluded.append({"org": oid, "kind": "phone", "value_masked": mask(x["number"]),
                                     "reason": "directory_of_other_contacts", "source_url": ""})
            phones = [x for x in phones if x["number"] in keepn]
            if not emails and not phones:
                continue
        allev = eev + pev
        contact_ev = [x for x in allev if re.search(r"(?i)contact|kontakt|contatt|contacto", x["source_url"])]
        primary = (contact_ev or allev)[0]
        orgs[oid] = {
            "id": oid, "name": o["name"], "layer": o["layer"], "node_type": o["node_type"], "scope": o["scope"],
            "website": o.get("url"), "country": o.get("country"),
            "emails": emails[:5], "phones": phones[:4],
            "contact_page_url": primary["source_url"], "snippet": primary["snippet"],
            "email_evidence": eev[:5],
            "phone_evidence": [{k: v for k, v in x.items() if k != "before"} for x in pev[:4]],
            "source_url": primary["source_url"], "retrieved": primary["retrieved"],
            "extracted_by": "automated",
        }
    return raw, orgs, excluded


def build_trials():
    raw = json.loads((RAW / "trials_extracted.json").read_text())
    trials, excluded = {}, []
    for nct, s in raw["studies"].items():
        s, removed = validate.filter_trial(dict(s))
        excluded += removed
        if s is None:
            continue
        countries = {l.get("country") for l in s["locations"] if l.get("country")}
        cc = COUNTRY_TO_CC.get(next(iter(countries))) if len(countries) == 1 else None
        for c in s["central_contacts"]:
            if c.get("phone"):
                c["e164"] = to_e164(c["phone"], cc)
        s["locations_count"] = len(s["locations"])
        s["locations"] = s["locations"][:60]
        trials[nct] = s
    return raw, trials, excluded


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    oraw, orgs, oex = build_orgs()
    traw, trials, tex = build_trials()
    n_email = sum(1 for o in orgs.values() if o["emails"])
    n_phone = sum(1 for o in orgs.values() if o["phones"])
    n_central = sum(1 for t in trials.values() if t["central_contacts"])
    n_c_email = sum(1 for t in trials.values() if any(c.get("email") for c in t["central_contacts"]))
    n_c_phone = sum(1 for t in trials.values() if any(c.get("phone") for c in t["central_contacts"]))
    targets = oraw["orgs"]
    scope = collections.Counter(t["scope"] for t in targets.values())
    with_site = sum(1 for t in targets.values() if t.get("url"))
    fl = oraw["meta"]["fetch_log"]
    fetch_stats = collections.Counter(l.get("result") for l in fl)
    reasons = collections.Counter(e["reason"] for e in oex)
    meta = {"built": TODAY, "privacy_rule": "Only contact details an organisation publishes for being contacted; "
            "trial contacts only from ClinicalTrials.gov centralContacts of recruiting / not-yet-recruiting studies.",
            "orgs_in_scope": len(targets), "orgs_with_website": with_site, "orgs_with_contact": len(orgs),
            "orgs_with_email": n_email, "orgs_with_phone": n_phone}
    (OUT / "orgs.json").write_text(json.dumps({"meta": meta, "orgs": orgs}, indent=1, ensure_ascii=False))
    tmeta = {"built": TODAY, "referenced_studies": traw["meta"]["referenced"],
             "current_status_counts": traw["meta"]["current_status_counts"],
             "recruiting_or_not_yet": len(trials), "with_central_contact": n_central,
             "central_email": n_c_email, "central_phone": n_c_phone}
    (OUT / "trials.json").write_text(json.dumps({"meta": tmeta, "trials": trials}, indent=1, ensure_ascii=False))
    (OUT / "exclusions.json").write_text(json.dumps(
        {"meta": {"note": "values are masked; nothing here is shown in the app", "by_reason": reasons},
         "orgs": oex, "trials": tex}, indent=1, ensure_ascii=False))
    bd = oraw["meta"].get("brightdata_requests", 0)
    bd_total = sum(1 for _ in open(RAW / "brightdata_usage.jsonl")) if (RAW / "brightdata_usage.jsonl").exists() else 0
    readme = f"""# Contact details: how families can reach groups and studies

Built {TODAY} by `pipeline/contacts/` (stdlib Python; raw data cached in `data/raw/contacts/`).
Everything is `extracted_by: "automated"`, and every entry carries `source_url` and `retrieved`.

## Privacy rule (strict)

We collect **only contact details that an organisation publishes so that it can be contacted**.

- **Patient organisations, registries, foundations:** the general contact email or phone on the
  organisation's own website (contact / about / footer), e.g. `info@...` or a helpline number.
- **Clinical trials:** only the **central contact** of the ClinicalTrials.gov record
  (`contactsLocationsModule.centralContacts`: name, role, phone, email) of a study whose *current*
  status is `RECRUITING` or `NOT_YET_RECRUITING`. Sponsors publish these so participants can reach the
  study. Overall officials keep only **affiliation + role** (no names). Locations keep only
  facility, city, state, country and status (site-level contacts are dropped).
- **Named people** only when the organisation itself publishes that person, on its own website, as a
  contact for the organisation (see "Named contact people" below, `people.json`).
- **Never**: researchers' emails or phones from papers or author lists; no combining of sources to find
  or complete a person's details; no guessed addresses.
- `validate.py` keeps only role mailboxes on the org's own domain (info@, contact@, support@, helpline@,
  membership@ ..., or the organisation's own acronym/name) and removes anything that looks personal: first.last@ or first-name mailboxes, addresses
  matching a person named next to them, free-mail addresses (gmail, yahoo, ...) not presented as the
  organisation's contact, addresses on a third-party domain, mobile numbers (UK 07/+447, DE +4915-17,
  FR +336/7, NL +316, IT +393 ...) unless labelled as the organisation's general/helpline number,
  phones shown next to a named person, fax numbers and placeholders. Snippets are scrubbed: any other
  email or phone inside a kept snippet becomes `[removed]`. Re-check the derived files any time with
  `python3 pipeline/contacts/validate.py` (removes offending values in place).

## Counts

| | |
|---|---|
| Orgs in scope (45 deep diseases + top 300 scale orgs by disease coverage) | {len(targets)} (deep {scope.get('deep', 0)}, top300 {scope.get('top300', 0)}) |
| ... with an own website (directory-only orgs have none) | {with_site} |
| Orgs with any contact | {len(orgs)} |
| Orgs with an email | {n_email} |
| Orgs with a phone | {n_phone} |
| Referenced CT.gov studies re-fetched | {traw['meta']['referenced']} |
| Currently recruiting / not yet recruiting | {len(trials)} |
| ... with a central contact | {n_central} (email {n_c_email}, phone {n_c_phone}) |
| Values excluded by the validator (orgs) | {len(oex)}: {', '.join(f'{k} {v}' for k, v in reasons.most_common())} |

Contact-page fetches (orgs whose stored pages had no usable contact; max 1 contact page each, found via
a "contact" link on the homepage, same host): {dict(fetch_stats)}. Bright Data Web Unlocker fallback
requests: {bd_total} (cap 150); everything else was a plain fetch. Pages fetched and cached in
`data/raw/contacts/web/` over all runs: {len(list((RAW / 'web').glob('*.json')))} (homepage re-reads + contact pages; the
stats above are from the last run, which only retried orgs still without a usable contact).

## Files

### `orgs.json`
`{{meta, orgs: {{<org id>: {{id, name, layer: graph|scale, node_type: patient_org|asset, scope: deep|top300,
website, country, emails[], phones[{{number, e164|null}}], contact_page_url, snippet, email_evidence[{{value,
source_url, snippet, how: mailto_link|visible_text, retrieved}}], phone_evidence[{{value, e164, source_url,
snippet, how: tel_link|visible_text, retrieved}}], source_url, retrieved, extracted_by}}}}}}`

Keys are the graph ids (`org:<slug>`, `asset:<slug>`) for deep-layer nodes and the scale org ids
(`org:<slug>` from `data/derived/scale/orgs.json`) otherwise. `e164` is set only when the country is
clear (org country, ccTLD, or an explicit `+` prefix); otherwise keep `number` as printed.

### `trials.json`
`{{meta, trials: {{<NCT>: {{nct, title, status, sponsor, central_contacts[{{name, role, phone, phoneExt, email,
e164}}], official_affiliations[{{role, affiliation}}], locations[{{facility, city, state, country, status}}]
(first 60), locations_count, source_url, api_url, retrieved}}}}}}`

### `exclusions.json`
Masked log of everything the validator removed (org id, kind, masked value, reason, page).

## Sources

1. Stored org pages: `data/raw/community/web`, `data/raw/families/*/web`,
   `data/raw/families/dee/community/web`, Bright Data unlocker caches, `data/raw/scale/pages`
   (text-only). Parsed: `mailto:`/`tel:` links, visible emails, phones on lines with a phone keyword,
   Cloudflare-obfuscated emails decoded.
2. Contact pages fetched here: `data/raw/contacts/web/` (when a stored homepage was text-only, the
   homepage was re-fetched once to read its links).
3. ClinicalTrials.gov API v2 (`filter.ids`, batches of 100): `data/raw/contacts/ctgov/`.

## Re-run
```
python3 pipeline/contacts/fetch_trials.py     # CT.gov, cached
python3 pipeline/contacts/extract_orgs.py     # stored pages + capped contact-page fetches, cached
python3 pipeline/contacts/build.py            # validate + write derived files
python3 pipeline/contacts/people.py           # named contact people (after build.py, which writes exclusions.json)
python3 pipeline/contacts/validate.py         # optional re-check of derived files (incl. people.json)
```

## Caveats
- Precision over recall: `orgs.json` keeps role mailboxes only; named people the org presents as its
  contact are in `people.json` (see below).
- Some stored pages had emails redacted at storage time (`[email-redacted]`); those orgs got a fresh
  contact-page fetch.
- Directory-only scale orgs (Global Genes / NORD profile, no own website) are not covered.
- Phone extraction from visible text needs a phone keyword on the same line; a few numbers may be
  mis-labelled (e.g. a fax listed without a label).
"""
    old = (OUT / "README.md").read_text() if (OUT / "README.md").exists() else ""
    if "<!-- people:start -->" in old:  # keep the section written by people.py
        readme = readme.rstrip() + "\n\n" + old[old.index("<!-- people:start -->"):old.index("<!-- people:end -->")] \
            + "<!-- people:end -->\n"
    (OUT / "README.md").write_text(readme)
    print(json.dumps({**meta, **tmeta, "excluded_org_values": len(oex), "reasons": reasons,
                      "fetch": fetch_stats, "brightdata": bd_total}, default=str, indent=1))


if __name__ == "__main__":
    main()
