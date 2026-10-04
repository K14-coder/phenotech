# Contact details: how families can reach groups and studies

Built 2026-10-04 by `pipeline/contacts/` (stdlib Python; raw data cached in `data/raw/contacts/`).
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
| Orgs in scope (45 deep diseases + top 300 scale orgs by disease coverage) | 473 (deep 229, top300 244) |
| ... with an own website (directory-only orgs have none) | 329 |
| Orgs with any contact | 210 |
| Orgs with an email | 174 |
| Orgs with a phone | 75 |
| Referenced CT.gov studies re-fetched | 4155 |
| Currently recruiting / not yet recruiting | 1555 |
| ... with a central contact | 1463 (email 1459, phone 1452) |
| Values excluded by the validator (orgs) | 265: malformed_email 60, personal_looking_mailbox 43, named_individual_phone 39, third_party_domain 27, personal_mobile 23, not_a_role_mailbox 20, freemail_not_presented_as_org_contact 18, fax_number 12, directory_of_other_contacts 12, personal_freemail_mailbox 7, placeholder_or_junk 3, unparseable_phone 1 |

Contact-page fetches (orgs whose stored pages had no usable contact; max 1 contact page each, found via
a "contact" link on the homepage, same host): {'no_contact_link': 49, 'ok': 45, 'fetch_failed': 1, 'homepage_refetch_failed': 8}. Bright Data Web Unlocker fallback
requests: 2 (cap 150); everything else was a plain fetch. Pages fetched and cached in
`data/raw/contacts/web/` over all runs: 393 (homepage re-reads + contact pages; the
stats above are from the last run, which only retried orgs still without a usable contact).

## Files

### `orgs.json`
`{meta, orgs: {<org id>: {id, name, layer: graph|scale, node_type: patient_org|asset, scope: deep|top300,
website, country, emails[], phones[{number, e164|null}], contact_page_url, snippet, email_evidence[{value,
source_url, snippet, how: mailto_link|visible_text, retrieved}], phone_evidence[{value, e164, source_url,
snippet, how: tel_link|visible_text, retrieved}], source_url, retrieved, extracted_by}}}`

Keys are the graph ids (`org:<slug>`, `asset:<slug>`) for deep-layer nodes and the scale org ids
(`org:<slug>` from `data/derived/scale/orgs.json`) otherwise. `e164` is set only when the country is
clear (org country, ccTLD, or an explicit `+` prefix); otherwise keep `number` as printed.

### `trials.json`
`{meta, trials: {<NCT>: {nct, title, status, sponsor, central_contacts[{name, role, phone, phoneExt, email,
e164}], official_affiliations[{role, affiliation}], locations[{facility, city, state, country, status}]
(first 60), locations_count, source_url, api_url, retrieved}}}`

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

<!-- people:start -->
## Named contact people (`people.json`)

Built 2026-10-04 by `pipeline/contacts/people.py`; re-checked by `validate.py`.

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
| Orgs with a named contact person | 27 (deep 21, top300 6) |
| Named contact people | 112 (with email 112, with phone 9) |
| Candidates rejected under the rule | 31: no_contact_in_same_block_on_org_domain 11, only_shared_org_mailbox 10, not_presented_as_contact 5, manual: contact for a third-party clinical genetics study team, not for the organisation 1, manual: hospital study-site coordinator, not a contact for the organisation 1, manual: hospital study-site research nurse, not a contact for the organisation 1, manual: contact for a third-party university study team, not for the organisation 1, org_website_is_a_subpage_of_another_site 1 |
| Earlier exclusions re-checked (`named_individual_phone`, `personal_looking_mailbox`) | 82: requalified 26, still excluded 56 (masked log: `exclusions_people_review.json`) |
| Team/contact/about/staff pages fetched for deep-disease orgs (max 1 per org host) | {'ok': 127, 'no_unfetched_page_link': 24, 'no_stored_homepage_html': 11} |
| Bright Data Web Unlocker requests for this layer | 4 (cap 100) |

### Format
`{meta, people: {<org id>: [{name, role, emails[], phones[], page_url, snippet, retrieved, removal_note}]}}`
(org ids as in `orgs.json`). In snippets, page lines are joined with ` | `, blocks from the same page with
` || `, a bio paragraph is shortened to `[...]`, and `(mailto: x)` marks an address the page publishes
behind a link (e.g. a name or a "Contact Kacie" button). All candidates with their decision: `data/raw/contacts/people_candidates.json`.

### Re-run
```
python3 pipeline/contacts/people.py            # add --no-fetch to use only cached pages
python3 pipeline/contacts/validate.py          # re-checks orgs.json, trials.json and people.json
```
<!-- people:end -->

## Contact-role filter

After `people.py`, run `python3 pipeline/contacts/filter_people.py`. It keeps only people shown in a contact role (family support, director, founder, coordinator and similar) and drops board members and advisors without a contact role (team decision, 2026-10-04).
