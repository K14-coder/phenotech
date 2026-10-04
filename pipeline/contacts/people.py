"""Named contact people that an organisation ITSELF publishes as its contact, on its OWN website.

Rule (enforced here and again in validate.filter_people):
 - the page is on the org's own website domain (same registrable domain as the org's `website`);
 - the page shows a person's name together with an email and/or phone in the SAME page block
   (a few consecutive lines), framed as a contact for the organisation (a contact role such as
   "family support coordinator", "founder", "executive director", or "contact ... at");
 - we keep exactly what that block publishes: name, role/title, the email(s)/phone(s) shown next to
   the person, plus org id, page url, the verbatim block as snippet, and the retrieved date;
 - ONE source only: the org's own page. Nothing is combined with papers, LinkedIn, search engines or
   other sites, and no address is guessed from a pattern;
 - people listed only as board members without contact details are skipped (no contact in block);
 - pages that say contact details are not for public use are skipped entirely;
 - manual decisions live in people_review.json (rejections with a reason); they are re-applied.

Data: re-uses every stored org page (see extract_orgs.load_pages) and, for orgs serving the 45 deep
diseases, fetches at most ONE not-yet-stored "contact / team / about us / staff" page linked from the
stored homepage (plain fetch, Bright Data Web Unlocker fallback capped at 100 requests in total, token
never printed). Fetches are cached in data/raw/contacts/web/.

Run: python3 pipeline/contacts/people.py [--no-fetch]
Writes data/derived/contacts/people.json and data/raw/contacts/people_candidates.json (all candidates
with accept/reject reasons), then refreshes the "Named contact people" section of the contacts README.
"""

import collections
import concurrent.futures as cf
import datetime
import json
import pathlib
import re
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import extract_orgs as E  # noqa: E402
import validate as V  # noqa: E402

ROOT = HERE.parents[1]
RAW = ROOT / "data" / "raw" / "contacts"
OUT = ROOT / "data" / "derived" / "contacts"
REVIEW = HERE / "people_review.json"
TODAY = datetime.date.today().isoformat()
BD_CAP = 100

NOT_PUBLIC = re.compile(r"(?i)(not (?:to be used |intended )?for (?:public|commercial|marketing) (?:use|distribution|purposes)|"
                        r"not for publication|for (?:internal|members'?) use only|"
                        r"(?:contact )?details (?:are |must )?not (?:to be )?(?:used|shared|published|passed on)|"
                        r"do not (?:use|share|publish) (?:these|this|the) (?:contact|email|details))")

ROLE_WORDS = (r"coordinator|co-ordinator|director|manager|founder|co-founder|president|chair(?:man|woman|person)?|"
              r"secretary|officer|liaison|executive|ceo|coo|cfo|nurse|advis[eo]r|administrator|lead|head of|"
              r"treasurer|trustee|ambassador|representative|contact person|specialist|navigator|"
              r"family support|parent support|patient support|outreach|helpline|volunteer|"
              r"koordinator|vorsitzende|vorstand|ansprechpartner|presidente|presidenta|coordinadora?|"
              r"responsable|directrice|directeur|pr[ée]sidente?|secr[ée]taire|tr[ée]sori[eè]re?|segretari[oa]|"
              r"voorzitter|secretaris|penningmeester|contactpersoon|board member|bestuurslid|chapter|"
              r"d[ée]l[ée]gu[ée]e?s?(?: r[ée]gionale?s?)?|delegad[oa]|trabajador[a]? social|directora|patron[oa]|[áa]rea social|psic[oó]log[oa]|"
              r"enfermer[oa]|infirmi[eè]re?|assistante? sociale?|social worker|psychologist|counsel+or")
_OP = re.compile(r"\b([A-ZÀ-Þ][a-zà-ÿ]+) (?:et|and|&|und|y|e) ([A-ZÀ-Þ][a-zà-ÿ]+)|\b([A-ZÀ-Þ][a-zà-ÿ]+) [A-ZÀ-Þ]{3,}\b")


class _OtherPerson:
    """A line naming people in a form find_name does not parse ("Martine et André GILLETTE")."""
    @staticmethod
    def search(line):
        if len(line) < 50 and re.search(r"\b[A-ZÀ-Þ][a-zà-ÿ'’-]+ [A-ZÀ-Þ]{2,}(?:[- ][A-ZÀ-Þ]{2,})?\b", line) \
                and not re.search(r"\b(?:USA|UK|EU|NF|MPS|CEO|COO|CFO|PhD|MD)\b", line):
            return True  # "Damien MULLER": French-style name with surname in capitals
        for m in _OP.finditer(line):
            ws = [w for w in m.groups() if w]
            if any(w.lower() in FIRST for w in ws):
                return True
        return False


OTHER_PERSON = _OtherPerson()
ROLE_RE = re.compile(r"(?i)\b(" + ROLE_WORDS + r")\b")
FRAMING = re.compile(r"(?i)(contact|get in touch|reach|write to|email|e-mail|call|questions|enquir|inquir|"
                     r"kontakt|contacto|contatt|contacter|ansprechpartner|neem contact)")
STOP = set("""foundation association society alliance network group trust fund charity inc ltd llc gmbh ev
contact contacts us our the team support family families research center centre institute university hospital
clinic program programme registry disease diseases syndrome syndromes project initiative council board committee
privacy policy terms home about news donate events event shop store login sign menu search close skip read more
learn united states kingdom america europe european national international global street road avenue suite box
floor building office email phone tel fax mobile website facebook twitter instagram linkedin youtube copyright
rights reserved all click here form submit send message newsletter subscribe give join volunteer get involved
vice president founder co-founder director secretary treasurer chair coordinator manager executive
officer lead head chief senior junior assistant
monday tuesday wednesday thursday friday saturday sunday january february march april may june july august
september october november december general enquiries inquiries media press partnership partnerships helpline
medical scientific advisory patient patients parent parents care resources resource community awareness day
fundraising fundraise campaign campaigns treatment therapy genetic rare cure hope life""".split())
NAME_TOK = r"[A-ZÀ-Þ][a-zà-ÿ'’]+(?:[A-ZÀ-Þ][a-zà-ÿ'’]+)?(?:-[A-ZÀ-Þ][a-zà-ÿ'’]+)?"  # Smith, VanHoutan, McGlocklin, Burkitt-Wright
PARTICLE = r"(?:van|von|de|der|den|da|di|du|la|le|del|dos|ten|ter|bin|al)"
NAME_RE = re.compile(r"(?:(?:Dr|Mrs|Mr|Ms|Prof|Mme|Sr|Sra)\.?\s+)?(" + NAME_TOK + r"(?:\s+[A-Z]\.)?(?:\s+" + PARTICLE
                     + r")*\s+" + NAME_TOK + r"(?:\s+" + NAME_TOK + r")?)")
INLINE_RE = re.compile(r"(?i:contact|email|e-mail|call|reach|write to)\s+(?:our\s+([a-z][a-z \-]{2,40}?),?\s+)?"
                       r"(" + NAME_TOK + r"(?:\s+" + NAME_TOK + r")?)\s*(?:,\s*([^,@()]{3,80}?)\s*)?,?\s+(?i:at|on|via|by)\b")
EXTRA_FIRST = set("""maria mario sabine stefan andreas michaela petra monika ursula birgit claudia silvia nadia
nadine nathalie isabelle sylvie christophe francois françois nicolas antoine olivier laurent valerie valérie
celine céline aurelie aurélie veronique véronique martine brigitte catherine agnes agnès sandrine stephanie
giuseppe giovanni francesco alessandro antonio roberta chiara federica valentina elisa simona laura paola
manuel carlos jorge pedro luis ana isabel marta cristina pilar beatriz monica mónica raquel rocio rocío alicia
inge ingrid annemarie marieke els anke femke sanne lotte bram joost jeroen wim kees henk erik niels lars
karin kristin kirsten linnea astrid sigrid jens morten anders mikkel tove heidi hanne sinead siobhan niamh aoife
ciara orla fiona morag eilidh kirsty gemma leanne kerry tracey tracy dawn joanne jo-anne louise lindsay lindsey
stacey jodi jody kristen kristy kristi krista tara tori allison alison erin shannon colleen kathy kathryn kerri
terri sherri sheri sherry dana robin robyn jamie leslie lesley kelsey courtney brooke paige morgan taylor
whitney meredith hillary hilary caroline carolyn marianne marion miriam naomi esther judith deborah debbie
susanne suzanne susie lynn lynne jen jenn jenny jennie becky becca vicky vicki nikki shelley shelly tammy
tamara tanya tonya sonia sonja ivan igor sergei olga natasha natalia irina svetlana yulia elena helena
ahmed mohamed mohammed ali fatima aisha omar hassan yusuf priya anita sunita raj rajesh amit ankit deepak
wei li ming yuki hiroshi kenji akiko keiko mei lin chen""".split())
FIRST = V.FIRST_NAMES | EXTRA_FIRST


def base(url_or_host):
    h = V.host_of(url_or_host) if "/" in (url_or_host or "") else (url_or_host or "")
    return V.base_domain(h) if h else ""


def good_name(name):
    toks = [t for t in re.split(r"\s+", name) if not re.fullmatch(PARTICLE, t)]
    if len(toks) < 1 or any(t.lower().strip("'’") in STOP for t in toks):
        return False
    if len(toks) >= 2 and all(len(t) <= 2 for t in toks):
        return False
    return True


def lines_of(page):
    text = page["text"]
    raw = page.get("html")
    if raw:
        if "cfemail" in raw or "email-protection" in raw:
            raw = E.decode_cfemail(raw)
        # <a href="mailto:x@org">Jane Doe</a>: the address is published behind the name; show both
        raw2 = re.sub(r"(?is)(<a\b[^>]*href\s*=\s*[\"']\s*mailto:([^\"'?]+)[^>]*>)((?:(?!</a>).)*?)</a>",
                      lambda m: m.group(1) + m.group(3) + (" (mailto: " + m.group(2).strip() + ")"
                                                           if "@" not in E.visible_text(m.group(3)) else "") + "</a>", raw)
        if raw2 != page["html"]:
            text = E.visible_text(raw2)
    return [l.strip() for l in text.split("\n") if l.strip()]


def contacts_in(line):
    emails = [m.group(0).strip(".").lower() for m in E.EMAIL_RE.finditer(line)]
    phones = []
    if E.PHONE_KW.search(line) or re.search(r"(?:^|\s)(?:\+|\(\d)", line) or re.fullmatch(r"[\d\s()+.\-/]{9,22}", line):
        for m in E.PHONE_RE.finditer(line):
            d = re.sub(r"\D", "", m.group(1))
            if 8 <= len(d) <= 15 and not re.fullmatch(r"(19|20)\d{2}", d[:4]) or (8 <= len(d) <= 15 and "+" in m.group(1)):
                phones.append(m.group(1).strip())
    return emails, phones


def find_name(line, next_line=""):
    """Return (name, role_on_line) if the line starts a person entry."""
    if len(line) > 160:
        return None
    m = NAME_RE.match(line)
    prefix_role = ""
    if m and ROLE_RE.search(m.group(1)):
        m = None
    if not m:
        pm = re.match(r"(?i)^(.{0,60}?\b(?:" + ROLE_WORDS + r"))\s+(?=[A-ZÀ-Þ])", line)
        m = NAME_RE.match(line, pm.end()) if pm else None
        if not m:
            return None
        prefix_role = pm.group(1)
    name = m.group(1)
    rest = line[m.end():].strip(" ,–—-|:()")
    if prefix_role and rest and not E.EMAIL_RE.search(rest) and not re.search(r"(?i)^(tel|phone|email|e-mail)", rest):
        return None  # "Director of X Smith Award ..." -- a sentence, not a contact line

    first = re.split(r"\s+", name)[0].lower()
    if not good_name(name) or ROLE_RE.search(name):
        return None
    role_next = bool(next_line) and len(next_line) < 90 and bool(ROLE_RE.search(next_line)) \
        and not E.EMAIL_RE.search(next_line)
    if first not in FIRST and not ROLE_RE.search(rest) and not (role_next and (not rest or E.EMAIL_RE.search(rest))) \
            and not prefix_role:
        return None
    # the line must be "Name", "Name, Role", "Name - Role", "Name (Role)", "Name: email" -- not a sentence
    if rest and not ROLE_RE.search(rest) and not re.fullmatch(r"(?:[A-Z]{2,5}\b[, ]*)*", rest) \
            and not E.EMAIL_RE.search(rest) and not re.search(r"(?i)^(e|t|tel|phone|email|e-mail)\s*[:.]", rest):
        return None
    role = rest if ROLE_RE.search(rest) else prefix_role
    role = E.EMAIL_RE.sub("", role).replace("(mailto: )", "")
    role = re.split(r"(?i)\b(?:e-?mail|tel|phone|t)\s*[:.]", role)[0].strip(" ,–—-|:()")
    return name, role


def is_contact_line(line):
    e, p = contacts_in(line)
    return bool(e or p) or "[email-redacted]" in line


def people_on_page(page, org):
    lines = lines_of(page)
    cands = []
    for i, line in enumerate(lines):
        emails, phones = contacts_in(line)
        if not (emails or phones):
            continue
        # contiguous contact lines after the first one belong to the same entry: walk back over them
        top = i
        while top - 1 >= 0 and is_contact_line(lines[top - 1]) and not find_name(lines[top - 1]):
            top -= 1
        found = None
        for m in INLINE_RE.finditer(line):  # "Contact our founder Maria at maria@org.org"
            if m.group(2).split()[0].lower() in FIRST and good_name(m.group(2)):
                found = (i, m.group(2), (m.group(1) or m.group(3) or "").strip(), "inline")
        if not found:
            short_seen = 0
            for j in range(top, -1, -1):
                if j < top and is_contact_line(lines[j]):
                    break  # another entry's contact line
                if len(lines[j]) > 200:
                    continue  # a bio paragraph between the name and the contact lines
                short_seen += 1
                if short_seen > 5:
                    break
                nxt = lines[j + 1] if j + 1 < len(lines) else ""
                fn = find_name(lines[j], nxt)
                if fn:
                    found = (j, fn[0], fn[1], "block")
                    break
                if j < top and OTHER_PERSON.search(lines[j]):
                    break  # e.g. "Martine et André GILLETTE": the contact belongs to someone not parsed
        if not found:
            continue
        j, name, role, how = found
        start, end = j, i
        # an address published only behind a link label (mailto icon, "Staff", "Contact Kacie") is
        # attributed to this person only if the label names the person or the address itself carries
        # the person's first or last name; otherwise the layout is ambiguous and the address is dropped
        toks = [t.lower() for t in re.split(r"[\s\-]+", name) if len(t) > 2]
        def attributed(e):
            mm = re.search(r"([^|()]{0,60})\(mailto: " + re.escape(e) + r"\)", line, re.I)
            if not mm:
                return True  # visible address
            label = mm.group(1).lower()
            local = re.sub(r"[^a-z]", "", e.split("@")[0].lower())
            plain = lambda w: re.sub(r"[^a-z]", "", w.translate(str.maketrans("áéíóúàèìòùäöüñç", "aeiouaeiouaounc")))  # noqa: E731
            return any(t in label for t in toks) or any(len(plain(t)) >= 3 and plain(t) in local for t in toks)
        emails = [e for e in emails if attributed(e)]
        if not emails and not phones:
            continue
        if not role:  # role on the line(s) right after the name, inside the block
            for k in range(j + 1, min(max(i, j + 2), j + 3, len(lines))):
                if ROLE_RE.search(lines[k]) and len(lines[k]) < 120 and not is_contact_line(lines[k]):
                    role, end = lines[k], max(end, k)
                    break
        # role / framing heading up to 3 lines above the name (stop at another entry's contact line)
        framed_above = False
        for k in range(j - 1, max(-1, j - 4), -1):
            if is_contact_line(lines[k]) and k == j - 1 and how != "inline":
                # list under a heading, e.g. "Contact | A | a@ | B | b@": keep looking for the heading
                continue
            if len(lines[k]) > 200:
                break
            if not role and ROLE_RE.search(lines[k]) and len(lines[k]) < 90 and not is_contact_line(lines[k]):
                role, start = lines[k], k
            if FRAMING.search(lines[k]) and not is_contact_line(lines[k]):
                framed_above, start = True, min(start, k)
                break
        def join(a):
            return " | ".join(l if len(l) <= 200 else l[:150].rsplit(" ", 1)[0] + " [...]" for l in lines[a:end + 1])
        block = join(start)
        if len(block) > 450:
            block = join(j)  # noqa
            if len(block) > 450:
                continue
        role = re.sub(r"\s+", " ", role).strip(" ,;|–—-")
        cands.append({"name": name, "role": role[:120], "emails": emails,
                      "phones": phones, "snippet": block, "how": how, "page_url": page["url"],
                      "retrieved": page.get("retrieved") or TODAY,
                      "framed": bool(role) or framed_above or bool(FRAMING.search(block)) or how == "inline"})
    # merge entries for the same person on the same page (also "Rebeca" into "Rebeca Chajon")
    merged = {}
    for c in sorted(cands, key=lambda c: -len(c["name"])):
        k = c["name"].lower()
        tgt = merged.get(k) or next((m for mk, m in merged.items() if " " not in k and mk.split()[0] == k
                                     and set(c["emails"]) <= set(m["emails"]) and c["emails"]), None)
        if tgt:
            tgt["emails"] = list(dict.fromkeys(tgt["emails"] + c["emails"]))
            tgt["phones"] = list(dict.fromkeys(tgt["phones"] + c["phones"]))
            if c["snippet"] not in tgt["snippet"] and len(tgt["snippet"]) < 900:
                tgt["snippet"] += " || " + c["snippet"]
            tgt["role"] = tgt["role"] or c["role"]
            tgt["framed"] = tgt["framed"] or c["framed"]
        else:
            merged[k] = dict(c)
    return list(merged.values())


# ---------------------------------------------------------------- fetching (deep orgs only)
CAT = [(3, re.compile(r"(?i)\b(team|staff|our people|who we are|meet the|personnel|equipe|équipe|equipo|mitarbeiter)\b|"
                      r"/(team|staff|our-team|meet-the-team|our-people|who-we-are|equipe|equipo)\b")),
       (2, re.compile(r"(?i)\bcontact|kontakt|contatt|contacto")),
       (1, re.compile(r"(?i)\babout( us)?\b|/about|chi-siamo|qui-sommes|quienes-somos|ueber-uns|over-ons"))]


def candidate_links(home_html, base_url, host):
    out = {}
    for m in re.finditer(r"(?is)<a\b[^>]*href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", home_html):
        href, label = m.group(1).strip(), E.visible_text(m.group(2))[:60]
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        absu = urllib.parse.urljoin(base_url, href).split("#")[0]
        if E.host_of(absu) != host or re.search(r"(?i)\.(pdf|jpe?g|png|docx?)$|form|press|media|donat|shop", absu):
            continue
        path = urllib.parse.urlsplit(absu).path
        if path in ("", "/"):
            continue
        for score, rx in CAT:
            if rx.search(label) or rx.search(path):
                out[absu] = max(out.get(absu, 0), score)
                break
    return sorted(out.items(), key=lambda kv: (-kv[1], len(kv[0])))


def fetch_one(org, pages_by_host, stored_urls):
    host = E.host_of(org["url"])
    homes = [p for p in pages_by_host.get(host, []) if p.get("html")]
    log = {"org": org["id"], "host": host}
    if not homes:
        log["result"] = "no_stored_homepage_html"
        return log, None
    links = []
    for h in homes:
        links += candidate_links(h["html"], h["url"], host)
    norm = lambda u: u.rstrip("/").replace("://www.", "://").lower()  # noqa: E731
    stored = {norm(u) for u in stored_urls}
    links = [(u, s) for u, s in dict(links).items() if norm(u) not in stored]
    links.sort(key=lambda kv: (-kv[1], len(kv[0])))
    if not links:
        log["result"] = "no_unfetched_page_link"
        return log, None
    url = links[0][0]
    log["url"] = url
    r = E.plain_fetch(url)
    if not E.good(r):
        r = E.bd_fetch(url)
        if not E.good(r):
            log["result"] = "fetch_failed"
            return log, None
        log["via"] = "brightdata"
    else:
        log["via"] = "direct"
    log["result"] = "ok"
    fu = r.get("final_url") or url
    return log, {"url": fu, "retrieved": r["retrieved"], "html": r["html"], "text": E.visible_text(r["html"]),
                 "host": E.host_of(fu), "fetched_here": True}


# ---------------------------------------------------------------- earlier exclusions
def review_exclusions(targets, people, cand_log):
    """Re-check values excluded earlier as 'named_individual_phone' or 'personal_looking_mailbox':
    they qualify now only if the org's own page presents that person as the org's contact (i.e. the
    value is in people.json for that org). Everything else stays masked and excluded. Writes a masked
    log to data/derived/contacts/exclusions_people_review.json."""
    from build import mask  # noqa: PLC0415
    exf = OUT / "exclusions.json"
    if not exf.exists():
        return {}
    ex = [e for e in json.loads(exf.read_text())["orgs"]
          if e["reason"] in ("named_individual_phone", "personal_looking_mailbox")]
    raw_by_mask = collections.defaultdict(list)
    for oid, t in targets.items():
        for ev in t.get("evidence", []):
            raw_by_mask[(oid, ev["kind"], mask(ev["value"]))].append(ev["value"])
    digits = lambda v: re.sub(r"\D", "", v)  # noqa: E731
    out, stats = [], collections.Counter()
    for e in ex:
        vals = raw_by_mask.get((e["org"], e["kind"], e["value_masked"]), [])
        hit = None
        for x in people.get(e["org"], []):
            for v in vals:
                if (e["kind"] == "email" and v.lower() in x["emails"]) or \
                        (e["kind"] == "phone" and any(digits(v) and digits(v)[-9:] == digits(p)[-9:] for p in x["phones"])):
                    hit = x
        if hit:
            decision = "requalified: presented by the org as its contact (" + (hit["role"] or "named contact") + ")"
        else:
            why = None
            for c in cand_log:
                if c["org"] == e["org"] and any(v.lower() in [m.lower() for m in c.get("emails") or []] or
                                                any(digits(v)[-9:] == digits(p)[-9:] for p in c.get("phones") or [])
                                                for v in vals):
                    why = c["decision"]
            if t := targets.get(e["org"]):
                if t.get("node_type") == "asset":
                    why = why or "asset node (registry/study); see its host org"
            decision = "still_excluded: " + (why or "no named person presented as the org's contact next to it")
        stats[decision.split(":")[0]] += 1
        out.append({**e, "decision": decision})
    (OUT / "exclusions_people_review.json").write_text(json.dumps(
        {"meta": {"note": "values stay masked; re-check of earlier 'named_individual_phone' and "
                          "'personal_looking_mailbox' exclusions under the named-contact rule", "counts": stats},
         "items": out}, indent=1, ensure_ascii=False))
    return dict(stats)


# ---------------------------------------------------------------- README section
START, END = "<!-- people:start -->", "<!-- people:end -->"


def write_readme_section(meta, people, targets, decisions, cand_log):
    n_people = sum(len(v) for v in people.values())
    scope = collections.Counter(targets[o]["scope"] for o in people)
    with_phone = sum(1 for v in people.values() for x in v if x["phones"])
    rejected = collections.Counter(c["decision"].split(":")[0] if not c["decision"].startswith("manual:") else
                                   "manual: " + c["decision"].split(": ", 2)[-1] for c in cand_log
                                   if not c["decision"].startswith("kept"))
    ex = meta.get("exclusions_review", {})
    sec = f"""{START}
## Named contact people (`people.json`)

Built {TODAY} by `pipeline/contacts/people.py`; re-checked by `validate.py`.

### Rule
A named person is included **only when the organisation itself publishes that person, on its own
website domain, as a contact for the organisation** -- e.g. a contact page listing "Family support
coordinator: Jane Doe, jane@org.org", "Contact our founder Maria at ...", or a "Get in touch" / team
block naming the person with an email or phone.

- We keep exactly what that page publishes: name, role/title and the email(s)/phone(s) shown next to the
  person, plus org id, page url, the verbatim page block as `snippet`, and the retrieved date.
- **One source only, the org's own page.** Nothing is combined from papers, LinkedIn, search engines or
  other sites; no address is guessed from a pattern.
- Skipped: people shown only as board members without contact details; pages saying contact details are
  not for public use; registries/studies (asset nodes: their host org's entry carries the people);
  contacts for third-party study teams listed on an org's site; researchers and clinicians from papers.
- `validate.filter_person` enforces: page on the same registrable domain as the org's website (and not a
  profile page on an umbrella site); name and each kept email/phone in the **same page block** (the
  snippet, max 450 characters per block); emails only on the org's own domain(s) or a free-mail address
  shown as that person's contact (a board member's private free-mail in a plain roster is dropped);
  addresses on employers'/universities' domains dropped; fax numbers dropped; any other email/phone in
  the snippet becomes `[removed]`. An address published only behind a link icon is attributed to a
  person only if the link label names them or the address carries their name; otherwise it is dropped
  as ambiguous. An address shared by 3+ people of one org (e.g. `admin@` next to every board member) is
  the org's general mailbox and is not shown as a person's contact.
- Manual decisions: `pipeline/contacts/people_review.json` (rejections with reasons; two additions for a
  two-person block the parser cannot split, re-checked against the stored page).

### Removal path
Every entry carries `removal_note`, which the UI shows next to the person:
"Shown as published by <org> on <url>. To correct or remove, contact the organisation or us via /privacy"

### Counts

| | |
|---|---|
| Orgs with a named contact person | {len(people)} (deep {scope.get('deep', 0)}, top300 {scope.get('top300', 0)}) |
| Named contact people | {n_people} (with email {sum(1 for v in people.values() for x in v if x['emails'])}, with phone {with_phone}) |
| Candidates rejected under the rule | {sum(rejected.values())}: {', '.join(f'{k} {v}' for k, v in rejected.most_common())} |
| Earlier exclusions re-checked (`named_individual_phone`, `personal_looking_mailbox`) | {sum(ex.values())}: requalified {ex.get('requalified', 0)}, still excluded {ex.get('still_excluded', 0)} (masked log: `exclusions_people_review.json`) |
| Team/contact/about/staff pages fetched for deep-disease orgs (max 1 per org host) | {meta['fetch']} |
| Bright Data Web Unlocker requests for this layer | {meta['brightdata_requests_fetch_run']} (cap 100) |

### Format
`{{meta, people: {{<org id>: [{{name, role, emails[], phones[], page_url, snippet, retrieved, removal_note}}]}}}}`
(org ids as in `orgs.json`). In snippets, page lines are joined with ` | `, blocks from the same page with
` || `, a bio paragraph is shortened to `[...]`, and `(mailto: x)` marks an address the page publishes
behind a link (e.g. a name or a "Contact Kacie" button). All candidates with their decision: `data/raw/contacts/people_candidates.json`.

### Re-run
```
python3 pipeline/contacts/people.py            # add --no-fetch to use only cached pages
python3 pipeline/contacts/validate.py          # re-checks orgs.json, trials.json and people.json
```
{END}
"""
    rf = OUT / "README.md"
    txt = rf.read_text() if rf.exists() else ""
    if START in txt:
        txt = txt[:txt.index(START)] + sec + txt[txt.index(END) + len(END) + 1:]
    else:
        txt = txt.rstrip() + "\n\n" + sec
    rf.write_text(txt)


# ---------------------------------------------------------------- main
def main():
    E.BD_BUDGET = BD_CAP
    bd_before = sum(1 for _ in open(RAW / "brightdata_usage.jsonl")) if (RAW / "brightdata_usage.jsonl").exists() else 0
    targets = json.loads((RAW / "orgs_extracted.json").read_text())["orgs"]
    pages = E.load_pages()
    pages_by_host = collections.defaultdict(list)
    for p in pages:
        pages_by_host[p["host"]].append(p)
    stored_urls = {p["url"] for p in pages}
    fetch_log, bd_used = [], 0
    if "--no-fetch" not in sys.argv:
        seen, todo = set(), []
        for t in targets.values():
            h = E.host_of(t["url"]) if t.get("url") else ""
            if t["scope"] == "deep" and h and h not in seen and h not in E.DIRECTORY_HOSTS:
                seen.add(h)
                todo.append(t)
        with cf.ThreadPoolExecutor(8) as ex:
            for log, page in ex.map(lambda o: fetch_one(o, pages_by_host, stored_urls), todo):
                fetch_log.append(log)
                if page:
                    pages_by_host[log["host"]].append(page)
                    if page["host"] != log["host"]:
                        pages_by_host[page["host"]].append(page)
        (RAW / "people_fetch_log.json").write_text(json.dumps({"brightdata_requests": E.BD_USED["n"],
                                                                "log": fetch_log}, indent=1))
        bd_used = E.BD_USED["n"]
    elif (RAW / "people_fetch_log.json").exists():
        fl = json.loads((RAW / "people_fetch_log.json").read_text())
        fetch_log, bd_used = fl["log"], fl.get("brightdata_requests", 0)

    review = json.loads(REVIEW.read_text()) if REVIEW.exists() else {"reject": []}
    rejects = {(r["org"], r["name"].lower()): r["reason"] for r in review.get("reject", [])}
    people, cand_log, page_skips = {}, [], []
    for oid, t in targets.items():
        if not t.get("url") or t.get("node_type") == "asset":
            continue  # registries / studies (asset nodes): their host org's entry carries the people
        host = E.host_of(t["url"])
        org = {**t, "website": t["url"]}
        seen_pages = set()
        for p in pages_by_host.get(host, []):
            if p["url"] in seen_pages:
                continue
            seen_pages.add(p["url"])
            if NOT_PUBLIC.search(p["text"] or ""):
                page_skips.append({"org": oid, "page_url": p["url"], "reason": "page_says_not_for_public_use"})
                continue
            for c in people_on_page(p, org):
                entry = {"name": c["name"], "role": c["role"], "emails": c["emails"], "phones": c["phones"],
                         "page_url": c["page_url"], "snippet": c["snippet"], "retrieved": c["retrieved"]}
                why = None
                if not c["framed"]:
                    why = "not_presented_as_contact"
                elif (oid, c["name"].lower()) in rejects:
                    why = "manual: " + rejects[(oid, c["name"].lower())]
                if why is None:
                    entry, why = V.filter_person(entry, org)
                cand_log.append({"org": oid, "name": c["name"], "role": c["role"], "page_url": c["page_url"],
                                 "snippet": c["snippet"][:300], "decision": "kept" if why is None else why,
                                 "emails": c["emails"], "phones": c["phones"]})
                if why is None:
                    lst = people.setdefault(oid, [])
                    if not any(x["name"].lower() == entry["name"].lower() for x in lst):
                        lst.append(entry)
    # manual additions (people_review.json "add"): only re-checked against the stored org page; the
    # snippet is rebuilt from that page and filter_person enforces the same rule
    for a in review.get("add", []):
        t = targets.get(a["org"])
        pg = next((p for p in pages_by_host.get(E.host_of(t["url"]) if t and t.get("url") else "", [])
                   if p["url"].rstrip("/") == a["page_url"].rstrip("/")), None)
        why = None if t and pg else "manual add: stored page not found"
        if not why:
            L = lines_of(pg)
            vals = [v.lower() for v in a.get("emails", [])] + [re.sub(r"\D", "", v) for v in a.get("phones", [])]
            st = next((k for k, l in enumerate(L) if a["name"].split()[-1] in l), None)
            en = None
            if st is not None:
                for k in range(st, min(len(L), st + 10)):
                    if any(v and (v in L[k].lower() or v in re.sub(r"\D", "", L[k])) for v in vals):
                        en = k
            if st is None or en is None:
                why = "manual add: name and values not in one block of the stored page"
            else:
                a0 = max(0, st - int(a.get("lines_before", 0)))
                entry = {"name": a["name"], "role": a.get("role", ""), "emails": a.get("emails", []),
                         "phones": a.get("phones", []), "page_url": pg["url"], "snippet": " | ".join(L[a0:en + 1]),
                         "retrieved": pg.get("retrieved") or TODAY}
                entry, why = V.filter_person(entry, {**t, "website": t["url"]})
                if not why:
                    lst = people.setdefault(a["org"], [])
                    lst[:] = [x for x in lst if x["name"].lower() != entry["name"].lower()] + [entry]
        cand_log.append({"org": a["org"], "name": a["name"], "page_url": a["page_url"],
                         "decision": "kept (manual add)" if why is None else why})

    # an address shared by >= 3 people on one org (e.g. admin@ next to every board member) is the org's
    # general mailbox (already in orgs.json), not a personal contact: drop it from the people; a person
    # left with nothing is skipped ("only_shared_org_mailbox"). First-name-only entries ("Rebeca")
    # merge into the full-name entry with the same address.
    for oid in list(people):
        lst = people[oid]
        cnt = collections.Counter(e for x in lst for e in set(x["emails"]))
        shared = {e for e, n in cnt.items() if n >= 3}
        keep = []
        for x in lst:
            if shared & set(x["emails"]):
                x = {**x, "emails": [e for e in x["emails"] if e not in shared]}
                x["snippet"] = V._scrub_multi(x["snippet"], x["emails"], x["phones"])
                if not x["emails"] and not x["phones"]:
                    cand_log.append({"org": oid, "name": x["name"], "page_url": x["page_url"],
                                     "decision": "only_shared_org_mailbox"})
                    continue
            full = next((y for y in keep if " " not in x["name"] and y["name"].split()[0] == x["name"]
                         and set(x["emails"]) <= set(y["emails"])), None)
            if full is None:
                keep.append(x)
        keep = [y for y in keep if not any(" " not in y["name"] and z is not y and z["name"].split()[0] == y["name"]
                                           and set(y["emails"]) <= set(z["emails"]) for z in keep)]
        if keep:
            people[oid] = keep
        else:
            del people[oid]
    meta = {
        "built": TODAY,
        "rule": "A named person is included only when the organisation itself publishes that person, on its own "
                "website domain, as a contact for the organisation (name and email/phone in the same page block). "
                "One source only; nothing combined from other sites; no guessed addresses.",
        "removal_note_template": "Shown as published by <org> on <url>. To correct or remove, contact the "
                                 "organisation or us via /privacy",
        "orgs_with_people": len(people), "people": sum(len(v) for v in people.values()),
        "fetch": dict(collections.Counter(l.get("result") for l in fetch_log)),
        "brightdata_requests_fetch_run": bd_used,
    }
    meta["exclusions_review"] = review_exclusions(targets, people, cand_log)
    names = {oid: t["name"] for oid, t in targets.items()}
    for oid, lst in people.items():
        for x in lst:
            x["removal_note"] = (f"Shown as published by {names[oid]} on {x['page_url']}. To correct or remove, "
                                 f"contact the organisation or us via /privacy")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "people.json").write_text(json.dumps({"meta": meta, "people": dict(sorted(people.items()))},
                                                indent=1, ensure_ascii=False))
    (RAW / "people_candidates.json").write_text(json.dumps({"page_skips": page_skips, "candidates": cand_log},
                                                           indent=1, ensure_ascii=False))
    decisions = collections.Counter(c["decision"].split(":")[0] for c in cand_log)
    write_readme_section(meta, people, targets, decisions, cand_log)
    print(json.dumps({**meta, "decisions": decisions, "page_skips": len(page_skips),
                      "bd_total_all_runs_before": bd_before}, indent=1, default=str))


if __name__ == "__main__":
    main()
