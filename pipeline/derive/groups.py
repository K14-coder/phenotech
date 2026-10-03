"""Disease grouping for guided search -> data/derived/global/groups.json  (index.json is not changed)

Run:  python3 pipeline/derive/groups.py        (stdlib; after global_index.py)
In:   data/raw/downloads/mondo-base.obo (is_a), data/derived/global/index.json
Rule for each index row's "family head" (nearest qualifying MONDO ancestor that is itself an index row):
  1. stem match: the nearest ancestor whose core name (name minus generic words such as disease,
     syndrome, type, form) is contained in the child's core name ("Gaucher disease" > "Gaucher
     disease type II", "Huntington disease" > "juvenile Huntington disease");
  2. otherwise the lowest ancestor with >= 2 index rows beneath it;
  3. never a root-like class: blocklisted generic names, or any ancestor with more than
     MAX_DESCENDANTS index rows beneath it, or within MIN_DEPTH is_a steps of the MONDO root.
  If nothing qualifies, the row is its own head.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque

from dcommon import DOWNLOADS, ROOT, TODAY, read_json, write_json

OUT = ROOT / "data" / "derived" / "global"
MAX_DESCENDANTS = 60
MIN_DEPTH = 3
GENERIC = re.compile(
    r"^(hereditary|inherited|genetic|rare|congenital|syndromic|non-syndromic|monogenic|familial|"
    r"autosomal (dominant|recessive)|x-linked)?\s*(rare )?(genetic |hereditary |inherited )?"
    r"(disease|disorder|syndrome|condition)s?( or disorder)?$|"
    r"(neurodegenerative|neurodevelopmental|metabolic|nervous system|musculoskeletal|skin|eye|ear|kidney|"
    r"cardiovascular|connective tissue|endocrine|immune system|blood|bone|lysosomal storage|"
    r"inborn errors? of metabolism|developmental defect|intellectual disability|epilepsy|cancer|neoplasm|"
    r"movement|myopathy|muscular dystrophy|neuropathy|leukodystrophy|ciliopathy|rasopathy|"
    r"channelopathy|cardiomyopathy|anemia|dwarfism|skeletal dysplasia)\b.*\b(disease|disorder)s?$|"
    r"^(human disease|disease or disorder|disease characteristic)$", re.I)
GENERIC_EXACT = {"intellectual disability", "epilepsy", "autism spectrum disorder", "cancer", "neoplasm",
                 "developmental and epileptic encephalopathy", "muscular dystrophy", "cardiomyopathy",
                 "lysosomal storage disease", "rasopathy", "ciliopathy", "leukodystrophy", "myopathy",
                 "neuropathy", "ataxia", "dystonia", "spastic paraplegia", "retinitis pigmentosa",
                 "congenital myasthenic syndrome", "spinocerebellar ataxia", "charcot-marie-tooth disease"}
STOP = {"disease", "syndrome", "disorder", "type", "form", "of", "the", "and", "with", "due", "to", "deficiency",
        "autosomal", "dominant", "recessive", "x", "linked", "x-linked", "a", "an", "in"}


def core(name):
    return [w for w in re.findall(r"[a-z0-9']+", name.lower().replace("'s", "")) if w not in STOP]


def parse_isa():
    parents, names, obsolete, cur = defaultdict(set), {}, set(), None
    for line in (DOWNLOADS / "mondo-base.obo").read_text().splitlines():
        if line == "[Term]":
            cur = {}
            continue
        if line.startswith("[") or not line:
            cur = None if line.startswith("[") else cur
            continue
        if cur is None:
            continue
        k, _, v = line.partition(": ")
        if k == "id":
            cur["id"] = v
        elif k == "name" and "id" in cur:
            names[cur["id"]] = v
        elif k == "is_a" and "id" in cur and v.startswith("MONDO:"):
            parents[cur["id"]].add(v.split(" ")[0])
        elif k == "is_obsolete" and v == "true" and "id" in cur:
            obsolete.add(cur["id"])
    return parents, names, obsolete


def distinction(child, head, genes):
    hc = set(core(head))
    rest = [w for w in re.findall(r"[A-Za-z0-9']+", child) if w.lower().replace("'s", "") not in hc
            and w.lower() not in {"disease", "syndrome", "disorder"}]
    txt = " ".join(rest).strip(" ,")
    txt = re.sub(r"^(type|form)\s*$", "", txt, flags=re.I)
    if re.fullmatch(r"([0-9]+[A-Za-z]?|[IVX]+)", txt):
        txt = f"type {txt}"
    if not txt and genes:
        txt = f"{genes} gene"
    elif genes and len(genes.split(",")) == 1 and genes.lower() not in txt.lower():
        txt = f"{txt} ({genes})" if txt else genes
    return txt or "same name in another source"


def main():
    idx = read_json(OUT / "index.json")
    F = {k: i for i, k in enumerate(idx["f"])}
    rows = {r[F["id"]]: r for r in idx["rows"]}
    parents, mnames, obsolete = parse_isa()
    in_index = set(rows)

    # depth from root(s) and number of index rows beneath every MONDO class
    children = defaultdict(set)
    for c, ps in parents.items():
        for p in ps:
            children[p].add(c)
    roots = [t for t in mnames if not parents.get(t) and t not in obsolete]
    depth = {}
    dq = deque((r, 0) for r in roots)
    while dq:
        t, d = dq.popleft()
        if t in depth and depth[t] <= d:
            continue
        depth[t] = d
        for c in children.get(t, ()):
            dq.append((c, d + 1))
    anc_memo = {}

    def ancestors(t):          # {ancestor: distance}
        if t in anc_memo:
            return anc_memo[t]
        out, dq2 = {}, deque([(p, 1) for p in parents.get(t, ())])
        while dq2:
            a, d = dq2.popleft()
            if a in out:
                continue
            out[a] = d
            dq2.extend((p, d + 1) for p in parents.get(a, ()))
        anc_memo[t] = out
        return out

    below = defaultdict(int)
    for r in in_index:
        for a in ancestors(r):
            below[a] += 1

    def blocked(a):
        nm = rows[a][F["name"]] if a in rows else mnames.get(a, "")
        return (GENERIC.search(nm) is not None or nm.lower() in GENERIC_EXACT or below[a] > MAX_DESCENDANTS
                or depth.get(a, 0) < MIN_DEPTH)

    head_of, basis = {}, {}
    for rid in in_index:
        if not rid.startswith("MONDO:"):
            head_of[rid] = rid
            continue
        anc = sorted(((d, a) for a, d in ancestors(rid).items() if a in in_index and not blocked(a)))
        cc = set(core(rows[rid][F["name"]]))
        stem = next((a for d, a in anc if set(core(rows[a][F["name"]])) and
                     set(core(rows[a][F["name"]])) <= cc), None)
        if stem:
            head_of[rid], basis[rid] = stem, "name stem"
            continue
        lowest = next((a for d, a in anc if below[a] >= 2), None)
        if lowest:
            head_of[rid], basis[rid] = lowest, "lowest ancestor with >= 2 index rows"
        else:
            head_of[rid] = rid
    # one level only: if a head itself has a stem head, collapse (A > B > C becomes A for C)
    for rid in list(head_of):
        h = head_of[rid]
        if h != rid and head_of.get(h, h) != h and basis.get(h) == "name stem":
            head_of[rid] = head_of[h]

    members = defaultdict(list)
    for rid, h in head_of.items():
        if h != rid:
            members[h].append(rid)
    groups = {}
    for h, ms in members.items():
        hname = rows[h][F["name"]]
        hcore = core(hname)
        mset = set(ms) | {h}
        similar = []
        if hcore and max(len(w) for w in hcore) >= 4:
            for rid, r in rows.items():
                if rid in mset or head_of.get(rid) in mset:
                    continue
                words = set(re.findall(r"[a-z0-9']+", r[F["name"]].lower().replace("'s", "")))
                if all(any(x.startswith(w) for x in words) for w in hcore):
                    similar.append(rid)
        groups[h] = {
            "name": hname, "genes": rows[h][F["genes"]], "n_members": len(ms),
            "members": sorted(({"id": m, "name": rows[m][F["name"]],
                                "distinction": distinction(rows[m][F["name"]], hname, rows[m][F["genes"]]),
                                "basis": basis.get(m)} for m in ms), key=lambda x: x["name"].lower()),
            "similar_names_different_conditions": sorted(similar, key=lambda x: rows[x][F["name"]].lower())[:12],
        }
    out = {
        "about": "Disease grouping for guided search: show the family head first, then ask which type. "
                 "Computed from MONDO is_a; index.json is unchanged.",
        "generated": TODAY,
        "rule": {"stem": "nearest is_a ancestor (in the index) whose core name is contained in the child's",
                 "fallback": "lowest is_a ancestor (in the index) with >= 2 index rows beneath it",
                 "never": f"blocklisted generic names, ancestors with > {MAX_DESCENDANTS} index rows beneath, or "
                          f"fewer than {MIN_DEPTH} is_a steps from the MONDO root",
                 "similar_names": "index rows containing every core word of the head's name but NOT under the "
                                  "head in MONDO: similar names, different conditions"},
        "counts": {"rows": len(head_of), "rows_with_a_head": sum(1 for r, h in head_of.items() if h != r),
                   "groups": len(groups)},
        "head_of": {r: h for r, h in sorted(head_of.items()) if h != r},
        "groups": dict(sorted(groups.items())),
    }
    size = write_json(OUT / "groups.json", out, compact=True)
    print(f"[groups] {out['counts']} ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
