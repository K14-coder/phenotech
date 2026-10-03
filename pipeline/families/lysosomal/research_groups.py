"""Up to 5 research groups per disease from recent PubMed papers (senior/last author), professional info only.

A paper qualifies if its TITLE names the disease (the title is the verbatim quote) and it is not a review,
erratum or comment. Groups = last author + institution (from the PubMed affiliation; e-mails redacted at fetch).
Ranked by number of qualifying 2021-2026 papers, then recency; a group needs >= 2 papers.
Run:  python3 pipeline/families/lysosomal/research_groups.py
Out:  data/raw/families/lysosomal/research/<GENE>.esearch.json, fragments/research.json, research/summary.json
"""
import re
from collections import defaultdict

import lyso_common as L

Q = {"GBA1": ("Gaucher", r"gaucher"), "GAA": ("Pompe", r"pompe"), "GLA": ("Fabry", r"fabry"),
     "HEXA": ("Tay-Sachs OR GM2 gangliosidosis", r"tay.?sachs|gm2"), "NPC1": ('"Niemann-Pick disease type C" OR "Niemann-Pick type C" OR NPC1', r"niemann.?pick (disease )?(type )?c|npc1?\b"),
     "SMPD1": ('"acid sphingomyelinase deficiency" OR "Niemann-Pick disease type B" OR olipudase', r"acid sphingomyelinase|niemann.?pick (disease )?(type )?(a|b)\b|olipudase"),
     "IDUA": ('"mucopolysaccharidosis type I" OR "MPS I" OR Hurler', r"mucopolysaccharidosis (type )?i\b|mps ?i\b|hurler"),
     "IDS": ('"mucopolysaccharidosis type II" OR "MPS II" OR "Hunter syndrome"', r"mucopolysaccharidosis (type )?ii\b|mps ?ii\b|hunter syndrome"),
     "CLN3": ("CLN3", r"cln3"), "TPP1": ('"CLN2 disease" OR CLN2', r"cln2"),
     "ARSA": ('"metachromatic leukodystrophy"', r"metachromatic"), "GALC": ('"Krabbe disease" OR Krabbe', r"krabbe")}
INST = re.compile(r"(Universit|Hospital|Institut|College|Center|Centre|School|Klinik|Clinic|Foundation|Hôpital|Ospedale|IRCCS)", re.I)


def inst_of(aff):
    parts = [p.strip(" .;") for p in re.split(r"[,;]", aff or "") if p.strip(" .;")]
    for pat in (r"Universit|Hospital|Hôpital|Ospedale|IRCCS|Institut|Klinik|Clinic|Foundation"):
        for p in parts:
            if re.search(pat, p, re.I) and not re.match(r"(Department|Dept|Division|Section|School|Faculty|Laboratory|Program|Unit|Center for|Centre for)\b", p, re.I):
                return p
    for p in parts:
        if INST.search(p) and not re.match(r"(Department|Dept|Division|Section|Laboratory of|Program|Unit)\b", p, re.I):
            return p
    return next((p for p in parts if INST.search(p)), parts[0] if parts else None)


def main():
    nodes, edges, summary = {}, {}, {}
    for gene, (q, rx) in Q.items():
        term = f"({q})[ti] AND 2021:2026[dp] NOT (review[pt] OR comment[pt] OR erratum[pt] OR editorial[pt])"
        ids = L.esearch_pubmed(term, retmax=80, sort="pub_date")
        L.write_json(L.RAW / "research" / f"{gene}.esearch.json", {"gene": gene, "term": term, "retrieved": L.TODAY, "ids": ids})
        recs = L.fetch_pmids(ids)
        groups = defaultdict(list)
        for pmid, r in recs.items():
            if not re.search(rx, r["title"], re.I) or any(t in ("Review", "Comment", "Erratum", "Editorial") for t in r["pub_types"]):
                continue
            au = [a for a in r["authors"] if a.get("last")]
            if not au or not au[-1].get("affiliations"):
                continue
            last = au[-1]
            inst = inst_of(last["affiliations"][0])
            if not inst:
                continue
            key = (last["last"], (last.get("fore") or "").split(" ")[0], L.slugify(inst, 50))
            groups[key].append((r, last, inst))
        ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), -max(x[0]["year"] or 0 for x in kv[1])))
        ranked = [kv for kv in ranked if len(kv[1]) >= 2][:5]
        summary[gene] = {"term": term, "n_hits": len(ids), "groups": [f"{k[1]} {k[0]} ({len(v)})" for k, v in ranked]}
        for (lastname, fore, islug), papers in ranked:
            r0, a0, inst = papers[0]
            name = f"{a0.get('fore') or ''} {lastname}".strip()
            rid = f"researcher:{L.slugify(name, 50)}--{islug}"
            attrs = {"affiliation": inst, "family": "lysosomal"}
            if a0.get("orcid"):
                attrs["orcid"], attrs["url"] = a0["orcid"], f"https://orcid.org/{a0['orcid']}"
            else:
                attrs["url"] = "https://pubmed.ncbi.nlm.nih.gov/?term=" + "+OR+".join(p[0]["pmid"] for p in papers[:20])
            nodes.setdefault(rid, {"id": rid, "type": "researcher", "label": name, "attrs": attrs})
            evs = [{"source": "PubMed", "ref": f"PMID:{p[0]['pmid']}", "url": p[0]["url"], "title": p[0]["title"],
                    "year": p[0]["year"], "quote": p[0]["title"], "kind": "publication", "extracted_by": "database",
                    "verified": False, "retrieved": L.TODAY} for p in papers[:5]]
            eid = f"{rid}|works_on|disease:{gene}"
            edges[eid] = {"id": eid, "source": rid, "target": f"disease:{gene}", "type": "works_on", "label": "works on",
                          "explanation": f"Last (senior) author on {len(papers)} papers since 2021 whose titles name this disease.",
                          "evidence_level": "observational", "status": "supported",
                          "confidence": 0.75 if len(papers) >= 3 else 0.65, "evidence": evs}
        print(gene, summary[gene]["groups"], flush=True)
    L.write_json(L.RAW / "fragments" / "research.json", {"nodes": list(nodes.values()), "edges": list(edges.values())})
    L.write_json(L.RAW / "research" / "summary.json", summary)


if __name__ == "__main__":
    main()
