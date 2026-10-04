"""Personal-data validator for contact details.

Policy: keep only contact details an ORGANISATION publishes so that it can be contacted.
 - Org sites: general/role mailboxes (info@, contact@, hello@ ...) and organisation phone lines.
   Removed: personal-looking mailboxes (first.last@, free-mail with no "contact us" framing),
   third-party domains, personal mobile numbers (unless framed as the org's helpline/contact line),
   fax numbers, junk/placeholder addresses.
 - Trials: only ClinicalTrials.gov centralContacts of RECRUITING / NOT_YET_RECRUITING studies.
   Overall officials keep affiliation + role only; locations keep facility/city/state/country/status.
 - Snippets are scrubbed: any email or phone in the snippet other than the kept value becomes
   "[removed]".

Usage as a library: filter_org_evidence(evidence, org), filter_trial(study) and filter_person(entry, org)
(named contact people: org-domain page, name + contact in the same block; see people.py).
CLI: python3 pipeline/contacts/validate.py  -> re-checks data/derived/contacts/*.json, removes any
offending value in place and prints what it removed.
"""

import json
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]

FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "hotmail.com",
            "hotmail.co.uk", "outlook.com", "live.com", "live.co.uk", "msn.com", "aol.com", "icloud.com",
            "me.com", "mac.com", "gmx.de", "gmx.net", "gmx.com", "web.de", "t-online.de", "orange.fr",
            "wanadoo.fr", "free.fr", "laposte.net", "libero.it", "btinternet.com", "sky.com",
            "protonmail.com", "proton.me", "mail.com", "comcast.net", "verizon.net", "att.net",
            "bigpond.com", "qq.com", "163.com", "yandex.ru", "mail.ru", "seznam.cz", "telenet.be",
            "ziggo.nl", "xs4all.nl", "hetnet.nl", "planet.nl", "home.nl", "bluewin.ch", "rocketmail.com"}
ROLE_TOKENS = ("info", "contact", "hello", "help", "support", "office", "admin", "enquir", "inquir", "mail",
               "team", "general", "famil", "member", "registry", "register", "research", "outreach", "program",
               "care", "advoca", "communic", "media", "press", "event", "donat", "fundrais", "volunteer",
               "partner", "secretar", "service", "connect", "study", "studies", "trial", "clinical", "patient",
               "parent", "community", "network", "foundation", "assoc", "society", "alliance", "news", "web",
               "kontakt", "contato", "contacto", "contatti", "secretariaat", "bureau", "accueil", "ask",
               "nurse", "line", "desk", "group", "uk", "us", "usa", "europe", "global", "intl", "international",
               "board", "director", "chair", "president", "coordinator", "manager", "grant", "science",
               "education", "awareness", "giving", "development", "finance", "accounts", "operations",
               "privacy", "data", "biobank", "info.")
CONTACT_CTX = re.compile(r"(?i)(contact us|contact|email us|e-mail us|write to us|get in touch|reach us|reach out|"
                         r"enquir|inquir|helpline|help line|support line|hotline|for families|family support|"
                         r"questions\??|general|office|kontakt|contactez|contacto)")
STRONG_CTX = re.compile(r"(?i)(contact us|email us|e-mail us|get in touch|helpline|help line|support line|hotline|"
                        r"freephone|call us|family support|for families|our office|main office|info line)")
JUNK = re.compile(r"(?i)(\.(png|jpe?g|gif|svg|webp|css|js|pdf)$|example\.(com|org|net)|sentry|wixpress|"
                  r"domain\.(com|org)|yourdomain|yoursite|@email\.com$|@2x|@3x|u00|godaddy|squarespace\.com|"
                  r"mysite|^test@|^name@|^user@|^username@|^you@|^your@|^john@|^jane@|^johndoe|firstname|lastname|"
                  r"^noreply|^no-reply|^donotreply|wordpress|cloudflare|schema\.org|@sentry|\.wixsite|"
                  r"@[0-9.]+$|@x\.com$|@yourcompany|^email@)")
# E.164 prefixes that are mobile ranges in countries where it is unambiguous.
MOBILE_PREFIXES = ("+447", "+3538", "+4915", "+4916", "+4917", "+336", "+337", "+316", "+614", "+346",
                   "+347", "+393", "+4175", "+4176", "+4177", "+4178", "+4179", "+467", "+474", "+479",
                   "+324", "+4366", "+4367", "+4368", "+351 9", "+3519", "+3584", "+3725", "+485", "+486",
                   "+487", "+488", "+64 2", "+642", "+9725", "+3859", "+407", "+3806", "+3807", "+3809",
                   "+4219", "+3579", "+3069", "+4206", "+4207", "+3620", "+3630", "+3670", "+5411 15", "+549", "+3816", "+79")
ORG_LINE = re.compile(r"(?i)(general|office|main|head office|helpline|support line|hotline|freephone|toll[- ]free|"
                      r"contact us|call us|switchboard|reception|info line|patient support)")
EMAIL_ANY = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_ANY = re.compile(r"\+?\(?\d[\d\s().\-]{7,}\d")


def host_of(url):
    h = (urllib.parse.urlsplit(url).hostname or "").lower() if url else ""
    return h[4:] if h.startswith("www.") else h


def base_domain(h):
    parts = h.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "org", "org", "com", "net", "ac", "gov", "or", "ne", "asn"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_role_local(local, org_host):
    lp = local.lower()
    if any(t in lp for t in ROLE_TOKENS):
        return True
    stem = base_domain(org_host).split(".")[0] if org_host else ""
    if stem and len(stem) >= 4 and (stem in lp or lp in stem):
        return True
    return False


FIRST_NAMES = set("""james john robert michael william david richard joseph thomas charles christopher daniel matthew
anthony mark donald steven paul andrew joshua kenneth kevin brian george timothy ronald edward jason jeffrey ryan jacob
gary nicholas eric jonathan stephen larry justin scott brandon benjamin samuel gregory alexander frank patrick raymond
jack dennis jerry tyler aaron jose adam nathan henry douglas zachary peter kyle noah ethan jeremy walter christian keith
roger terry austin sean gerald carl harold dylan arthur lawrence jordan jesse bryan billy bruce gabriel joe logan alan
juan albert willie elijah wayne randy vincent mason roy ralph bobby russell bradley philip eugene mary patricia jennifer
linda elizabeth barbara susan jessica sarah karen lisa nancy betty sandra margaret ashley kimberly emily donna michelle
carol amanda melissa deborah stephanie dorothy rebecca sharon laura cynthia amy kathleen angela shirley brenda emma anna
pamela nicole samantha katherine christine helen debra rachel carolyn janet maria catherine heather diane olivia julie
joyce victoria ruth virginia lauren kelly christina joan evelyn judith andrea hannah megan cheryl jacqueline martha
madison teresa gloria sara janice ann kathryn abigail sophia frances jean alice judy isabella julia grace amber denise
danielle marilyn beverly charlotte natalie theresa diana brittany doris kayla alexis lori marie katie kate kim mel
melanie tina jill wendy holly claire clare chris sam alex jo liz beth tom tim jim bob mike dan dave steve rob ben nick
matt pete phil tony andy ed fred greg jeff ken ron ray joel lucy sophie chloe ellie amelia ella jane anne annie rose
ruby lily molly hilde hans jan peter pieter marco luca giulia francesca anna sofia pierre marie sophie jean luc
camille julien thomas lukas leon finn paula elena carmen pablo javier lucia miguel rafael rebeca rebecca katerina ami alli rene ivana vanja milica marija jelena ana""".split())


EXTRA_ROLE = {"geral", "socios", "konkurs", "question", "questions", "photos", "brandcomms", "jobs", "feedback",
              "give", "impact", "hope", "post", "marketing", "comunicacion", "atencionfamilias", "fundacion",
              "ledenadministratie", "gs", "p.datos", "datos", "science", "programs", "secretariat"}


def acronym_ok(local, org):
    lp = re.sub(r"[^a-z0-9]", "", local.lower())
    name = (org.get("name") or "") if isinstance(org, dict) else ""
    words = re.findall(r"[A-Za-z0-9]+", name)
    initials = "".join(w[0] for w in words).lower()
    caps = "".join(w[0] for w in words if w[0].isupper() or w.isupper()).lower()
    acr = {a for a in re.findall(r"\b[A-Z0-9]{2,8}\b", name)}
    return bool(lp) and (lp in initials or lp in caps or lp.upper() in acr or (len(lp) >= 3 and lp in name.lower().replace(" ", "")))


def whitelisted_local(local, org_host, org):
    lp = local.lower()
    if lp in EXTRA_ROLE or is_role_local(local, org_host) or acronym_ok(local, org):
        return re.sub(r"[^a-z]", "", lp) not in FIRST_NAMES
    stem = org_host.replace("-", "") if org_host else ""
    return len(lp) >= 3 and re.sub(r"[^a-z0-9]", "", lp) in stem


def personal_looking_local(local, snippet=""):
    lp = local.lower()
    letters = re.sub(r"[^a-z]", "", lp)
    if re.fullmatch(r"[a-z]{2,}[._-][a-z]{2,}(\d{0,4})", lp) and not any(t in lp for t in ROLE_TOKENS[:20]):
        return True
    if letters in FIRST_NAMES or lp.split(".")[0] in FIRST_NAMES:
        return True
    # name words shown next to the address: "Katie Smith ... ksmith@", "Bruce Heger ... bruceheger@"
    names = re.findall(r"\b([A-Z][a-z]{1,20})\b", snippet or "")
    low = [n.lower() for n in names]
    for i, n in enumerate(low):
        if len(n) >= 3 and (letters == n or (letters.endswith(n) and len(letters) - len(n) <= 2)):
            return True
        if i + 1 < len(low) and letters in (n + low[i + 1], n[0] + low[i + 1], n + low[i + 1][0]):
            return True
    return False


def scrub(snip, keep_value):
    def rep_email(m):
        return m.group(0) if m.group(0).lower() == keep_value.lower() else "[removed]"

    keep_digits = re.sub(r"\D", "", keep_value)

    def rep_phone(m):
        d = re.sub(r"\D", "", m.group(0))
        if len(d) < 8 or (keep_digits and (d in keep_digits or keep_digits in d)):
            return m.group(0)
        return "[removed]"
    return PHONE_ANY.sub(rep_phone, EMAIL_ANY.sub(rep_email, snip or ""))


def check_email(ev, org):
    email = ev["value"].strip().strip(".").lower()
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,24}", email):
        return None, "malformed_email"
    if JUNK.search(email):
        return None, "placeholder_or_junk"
    local, dom = email.split("@", 1)
    org_host = host_of(org.get("url") or "")
    snip = ev.get("snippet") or ""
    before = ev.get("before")
    if before is None:
        pos = snip.lower().find(email)
        before = snip[max(0, pos - 90):pos] if pos >= 0 else snip[:120]
    same_org = bool(org_host) and (base_domain(dom) == base_domain(org_host))
    personal = personal_looking_local(local, snip)
    if dom in FREEMAIL and any(len(n) >= 4 and re.sub(r"[^a-z]", "", local).startswith(n) for n in FIRST_NAMES):
        personal = True  # michellesmith@gmail.com
    if personal and is_role_local(local, org_host) and not re.fullmatch(r"[a-z]{2,}[._-][a-z]{2,}\d*", local) \
            and re.sub(r"[^a-z]", "", local) not in FIRST_NAMES:
        personal = False  # e.g. contact@ / support@ whose word also appears capitalised on the page
    if dom in FREEMAIL:
        if personal and not is_role_local(local, org_host):
            return None, "personal_freemail_mailbox"
        if not (STRONG_CTX.search(before) or (is_role_local(local, org_host) and CONTACT_CTX.search(snip))):
            return None, "freemail_not_presented_as_org_contact"
        return email, None
    if not same_org:
        if org_host and base_domain(org_host).startswith(dom):
            return None, "malformed_email"  # truncated domain, e.g. info@x.or
        if is_role_local(local, org_host) and not personal and CONTACT_CTX.search(snip):
            return email, None
        return None, "third_party_domain"
    if personal and not (STRONG_CTX.search(before) and is_role_local(local, org_host)):
        return None, "personal_looking_mailbox"
    if not whitelisted_local(local, org_host, org):
        return None, "not_a_role_mailbox"
    return email, None


def check_phone(ev, org):
    e164 = ev.get("e164")
    digits = re.sub(r"\D", "", ev["value"])
    snip = ev.get("snippet") or ""
    raw = ev["value"]
    if ev.get("before") is None:  # re-check of derived data: rebuild the left context from the snippet
        pos = snip.find(raw)
        ev = {**ev, "before": snip[:pos] if pos >= 0 else "", "_recheck": True}
    before = (ev.get("before") or "")[-40:]
    if re.search(r"(?i)fax\b[^0-9]{0,6}$", before):
        return None, "fax_number"
    if re.search(r"(?i)(mobile|cell|mob\.?)\b[^0-9]{0,6}$", before):
        if not STRONG_CTX.search(snip):
            return None, "personal_mobile"
    if e164 and e164.startswith(MOBILE_PREFIXES) and not (STRONG_CTX.search(snip) or ORG_LINE.search(before)):
        return None, "personal_mobile"
    wide = ev.get("before") or ""
    named = re.search(r"\b([A-Z][a-z]+)\s+(?:[a-z]{1,3}\s+){0,2}([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b,?\s*(?:[A-Z]{2,4}\b,?\s*)?"
                      r"(President|Vice|Founder|Co-Founder|Secretary|Treasurer|Chair|Coordinator|Director|Manager|"
                      r"PhD|MD|MS|RN|MSc|Dad|Mom|Mum|Study|Research|Nurse|Genetic|Board)", wide)
    first = [m for m in re.finditer(r"\b([A-Z][^\W\d_]+)\s+(?:[a-z]{1,3}\s+){0,2}([A-Z][^\W\d_]+)", wide[-70:])
             if m.group(1).lower() in FIRST_NAMES]
    if re.search(r"(?i)contact:?\s*[A-Z][^\W\d_]+\s+(?:[a-z]{1,3}\s+){0,2}[A-Z][^\W\d_]+", wide[-90:]) or \
            re.search(r"[A-Z][^\W\d_]+ [A-Z][^\W\d_]+\s+(Tel|Phone|T)\s*[:.]\s*$", wide):
        first = first or [True]
    if (named or first) and not ORG_LINE.search(before) and not ev.get("_recheck"):
        return None, "named_individual_phone"
    if not e164 and not 9 <= len(digits) <= 11:
        return None, "unparseable_phone"
    if not e164 and len(digits) < 9:
        return None, "unparseable_phone"
    if re.fullmatch(r"(\d)\1{6,}", digits) or digits in ("1234567890", "0123456789"):
        return None, "placeholder_or_junk"
    return raw, None


def filter_org_evidence(evidence, org):
    kept, removed = [], []
    for ev in evidence:
        val, why = (check_email if ev["kind"] == "email" else check_phone)(ev, org)
        if why:
            removed.append({**ev, "reason": why})
        else:
            ev = {**ev, "value": val, "snippet": scrub(ev.get("snippet"), ev["value"])}
            kept.append(ev)
    return kept, removed


ALLOWED_CENTRAL = {"name", "role", "phone", "phoneExt", "email", "e164"}


def filter_trial(study):
    removed = []
    if study.get("status") not in ("RECRUITING", "NOT_YET_RECRUITING"):
        return None, [{"nct": study.get("nct"), "reason": "not_recruiting"}]
    cc = []
    for c in study.get("central_contacts", []):
        c = {k: v for k, v in c.items() if k in ALLOWED_CENTRAL}
        if c.get("email") and (JUNK.search(c["email"]) or "@" not in c["email"]):
            removed.append({"nct": study["nct"], "value": c.pop("email"), "reason": "placeholder_or_junk"})
        if c.get("email") or c.get("phone"):
            cc.append(c)
    study["central_contacts"] = cc
    study["official_affiliations"] = [{k: o[k] for k in ("role", "affiliation") if o.get(k)}
                                      for o in study.get("official_affiliations", [])]
    study["locations"] = [{k: l[k] for k in ("facility", "city", "state", "country", "status") if l.get(k)}
                          for l in study.get("locations", [])]
    return study, removed


# ---------------------------------------------------------------- named contact people (people.json)
PEOPLE_BLOCK_MAX = 450
NOT_PUBLIC_RE = re.compile(r"(?i)(not (?:to be used |intended )?for (?:public|commercial|marketing) (?:use|distribution|purposes)|"
                           r"not for publication|for (?:internal|members'?) use only|"
                           r"(?:contact )?details (?:are |must )?not (?:to be )?(?:used|shared|published|passed on))")


def _scrub_multi(snip, keep_emails, keep_phones):
    ke = {e.lower() for e in keep_emails}
    kd = [re.sub(r"\D", "", p) for p in keep_phones]

    def rep_email(m):
        return m.group(0) if m.group(0).lower().strip(".") in ke else "[removed]"

    def rep_phone(m):
        d = re.sub(r"\D", "", m.group(0))
        if len(d) < 8 or any(k and (d in k or k in d) for k in kd):
            return m.group(0)
        return "[removed]"
    return PHONE_ANY.sub(rep_phone, EMAIL_ANY.sub(rep_email, snip or ""))


def filter_person(entry, org):
    """Rule: the org itself publishes this person, on its OWN website domain, as a contact; name and
    contact value(s) in the same page block (the snippet). Returns (entry|None, reason|None)."""
    site = org.get("website") or org.get("url") or ""
    org_host = host_of(site)
    page_host = host_of(entry.get("page_url") or "")
    if not org_host or not page_host or base_domain(page_host) != base_domain(org_host):
        return None, "page_not_on_org_domain"
    site_path = urllib.parse.urlsplit(site).path.strip("/")
    if site_path.count("/") >= 1 and not urllib.parse.urlsplit(entry["page_url"]).path.strip("/").startswith(site_path):
        # the org's "website" is a profile/sub-page on someone else's site (umbrella directory) or a
        # registry hosted by a parent org: the people on that domain are not this entry's contacts
        return None, "org_website_is_a_subpage_of_another_site"
    name = (entry.get("name") or "").strip()
    snip = entry.get("snippet") or ""
    if not name or len(name) > 60:
        return None, "no_name"
    if NOT_PUBLIC_RE.search(snip):
        return None, "page_says_not_for_public_use"
    blocks = snip.split(" || ")
    if any(len(b) > PEOPLE_BLOCK_MAX for b in blocks):
        return None, "block_too_long"
    emails, phones = [], []
    for e in entry.get("emails") or []:
        e = e.strip().strip(".").lower()
        local, _, dom = e.partition("@")
        if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,24}", e) or JUNK.search(e):
            continue
        if base_domain(dom) != base_domain(org_host) and dom not in FREEMAIL and not org_named_domain(dom, org):
            continue  # address on someone else's domain (employer, university): not the org's contact
        if not any(name_in(name, b) and e in b.lower() for b in blocks):
            continue  # name and address must sit in the same block
        if dom in FREEMAIL and BOARD_ONLY.fullmatch((entry.get("role") or "").strip()) and not PERSON_CTX.search(snip):
            continue  # a board member's private mailbox listed in a board roster, not presented as a contact
        emails.append(e)
    for ph in entry.get("phones") or []:
        d = re.sub(r"\D", "", ph)
        hit = [b for b in blocks if name_in(name, b) and d and d in re.sub(r"\D", "", b)]
        if not hit or not 8 <= len(d) <= 15:
            continue
        b = hit[0]
        pos = b.find(ph)
        if pos >= 0 and re.search(r"(?i)fax\b[^0-9]{0,6}$", b[:pos][-30:]):
            continue
        phones.append(ph)
    if not emails and not phones:
        return None, "no_contact_in_same_block_on_org_domain"
    out = {**entry, "name": name, "emails": emails, "phones": phones,
           "snippet": _scrub_multi(snip, emails, phones)}
    return out, None


BOARD_ONLY = re.compile(r"(?i)(?:board member|director|trustee|treasurer|secretary|vice[- ]president|member|)")
PERSON_CTX = re.compile(r"(?i)(contact|get in touch|reach|write to|email us|questions|enquir|inquir|kontakt|contatt)")


def org_named_domain(dom, org):
    """A second domain of the same organisation, e.g. kinslowfoundation.org for 'Kinslow TUBB4a Foundation'."""
    stem = re.sub(r"[^a-z0-9]", "", base_domain(dom).split(".")[0])
    words = re.findall(r"[a-z0-9]+", (org.get("name") or "").lower())
    if len(stem) < 5 or re.search(r"(univ|hospital|health|clinic|nhs|edu|med|ac$)", stem):
        return False
    squashed = "".join(words)
    return stem in squashed or any(stem.startswith(w) and len(w) >= 5 and stem[len(w):] in squashed for w in words)


def name_in(name, block):
    toks = [t for t in re.split(r"\s+", name) if len(t) > 1]
    return all(t.lower() in block.lower() for t in toks)


def check_people_file(d, orgs_meta):
    """Re-check data/derived/contacts/people.json in place."""
    pf = d / "people.json"
    if not pf.exists():
        return 0
    pj = json.loads(pf.read_text())
    n = 0
    for oid in list(pj["people"]):
        org = orgs_meta.get(oid) or {}
        keep = []
        for x in pj["people"][oid]:
            y, why = filter_person(x, org)
            if why:
                print("REMOVE person", oid, x.get("name", "")[:1] + "***", why)
                n += 1
                continue
            if y["emails"] != x["emails"] or y["phones"] != x["phones"]:
                print("TRIM person", oid, x.get("name", "")[:1] + "***")
                n += 1
            if not y.get("removal_note") or y["page_url"] not in y["removal_note"] or "/privacy" not in y["removal_note"]:
                print("MISSING removal note", oid)
                n += 1
                y["removal_note"] = (f"Shown as published by {org.get('name', oid)} on {y['page_url']}. To correct or "
                                     f"remove, contact the organisation or us via /privacy")
            keep.append(y)
        if keep:
            pj["people"][oid] = keep
        else:
            del pj["people"][oid]
    if n and "--dry" not in sys.argv:
        pj["meta"]["orgs_with_people"] = len(pj["people"])
        pj["meta"]["people"] = sum(len(v) for v in pj["people"].values())
        pf.write_text(json.dumps(pj, indent=1, ensure_ascii=False))
    return n


def main():
    d = ROOT / "data" / "derived" / "contacts"
    orgs = json.loads((d / "orgs.json").read_text())
    n_removed = 0
    for oid, o in orgs["orgs"].items():
        ev = [{"kind": "email", **e} for e in o.get("email_evidence", [])] + \
             [{"kind": "phone", **p} for p in o.get("phone_evidence", [])]
        kept, removed = filter_org_evidence(ev, {**o, "url": o.get("website")})
        for r in removed:
            print("REMOVE", oid, r["kind"], r["value"], r["reason"])
            n_removed += 1
        if removed:
            bad = {r["value"] for r in removed}
            o["emails"] = [e for e in o["emails"] if e not in bad]
            o["phones"] = [p for p in o["phones"] if p["number"] not in bad]
            o["email_evidence"] = [e for e in o["email_evidence"] if e["value"] not in bad]
            o["phone_evidence"] = [p for p in o["phone_evidence"] if p["value"] not in bad]
    trials = json.loads((d / "trials.json").read_text())
    for nct in list(trials["trials"]):
        s, removed = filter_trial(trials["trials"][nct])
        for r in removed:
            print("REMOVE", nct, r)
            n_removed += 1
        if s is None:
            del trials["trials"][nct]
    targets = json.loads((ROOT / "data/raw/contacts/orgs_extracted.json").read_text())["orgs"] \
        if (ROOT / "data/raw/contacts/orgs_extracted.json").exists() else {}
    om = {k: {"name": t["name"], "website": t.get("url")} for k, t in targets.items()}
    for k, o in orgs["orgs"].items():
        om.setdefault(k, {"name": o["name"], "website": o.get("website")})
    n_removed += check_people_file(d, om)
    if n_removed and "--dry" not in sys.argv:
        (d / "orgs.json").write_text(json.dumps(orgs, indent=1, ensure_ascii=False))
        (d / "trials.json").write_text(json.dumps(trials, indent=1, ensure_ascii=False))
    print("validator: removed", n_removed)


if __name__ == "__main__":
    main()
