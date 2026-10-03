"""Monogenic disease universe for the breadth layer.

Inputs (read-only):
  data/raw/downloads/genes_to_disease.txt   HPO release: gene <-> OMIM/ORPHA disease, association type
  data/raw/downloads/phenotype.hpoa         disease names
  data/derived/global/index.json            (optional, parallel agent) MONDO id + synonyms per OMIM/ORPHA id
  Orphanet product6 (en_product6.xml)       downloaded once to data/raw/scale/orphanet/ to recover the
                                            gene-disease association TYPE that genes_to_disease.txt flattens
                                            to UNKNOWN for every ORPHA row.
Rules:
  OMIM rows: keep association_type == MENDELIAN.
  ORPHA rows: keep only if Orphanet product6 types the same gene-disease pair as
              "Disease-causing germline mutation(s) [(loss|gain) of function] in" with status Assessed.
Output: data/derived/scale/universe.json
"""
from __future__ import annotations

import collections
import csv
import gzip
import re
import xml.etree.ElementTree as ET

from common import DL, GLOBAL_INDEX, OUT, RAW, http, read_json, today, write_json

P6_URL = "https://www.orphadata.com/data/xml/en_product6.xml"
P6 = RAW / "orphanet" / "en_product6.xml.gz"


def load_product6():
    if not P6.exists():
        st, body, _ = http(P6_URL, timeout=120)
        if st != 200:
            raise RuntimeError(f"product6 download failed: {st}")
        P6.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(P6, "wb") as f:
            f.write(body)
    with gzip.open(P6, "rb") as f:
        root = ET.parse(f).getroot()
    assoc = {}   # (ORPHA:code, symbol) -> (type, status)
    names = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        names[f"ORPHA:{code}"] = d.findtext("Name") or ""
        for a in d.iter("DisorderGeneAssociation"):
            sym = a.findtext("Gene/Symbol")
            typ = a.findtext("DisorderGeneAssociationType/Name") or ""
            stat = a.findtext("DisorderGeneAssociationStatus/Name") or ""
            if sym:
                assoc[(f"ORPHA:{code}", sym)] = (typ, stat)
    return assoc, names


CAUSAL_ORPHA = re.compile(r"^Disease-causing germline mutation\(s\)", re.I)


def main():
    p6, p6names = load_product6()

    names = {}
    n_hpo = collections.Counter()
    with open(DL / "phenotype.hpoa") as f:
        for line in f:
            if line.startswith("#") or line.startswith("database_id"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            names.setdefault(parts[0], parts[1])
            if len(parts) > 10 and parts[10] == "P" and parts[2] != "NOT":
                n_hpo[parts[0]] += 1

    diseases = {}
    dropped = collections.Counter()
    with open(DL / "genes_to_disease.txt") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            did, sym, typ = row["disease_id"], row["gene_symbol"], row["association_type"]
            if did.startswith("OMIM:"):
                if typ != "MENDELIAN":
                    dropped[f"OMIM:{typ}"] += 1
                    continue
                rule = "HPO genes_to_disease association_type=MENDELIAN"
            elif did.startswith("ORPHA:"):
                t, s = p6.get((did, sym), ("", ""))
                if not (CAUSAL_ORPHA.match(t) and s.lower() == "assessed"):
                    dropped[f"ORPHA:{t or 'not in product6'}|{s}"] += 1
                    continue
                rule = f"Orphanet product6: {t} ({s})"
            else:
                continue
            d = diseases.setdefault(did, {"id": did, "name": names.get(did) or p6names.get(did) or "",
                                          "genes": [], "gene_rules": {}})
            if sym not in d["genes"]:
                d["genes"].append(sym)
                d["gene_rules"][sym] = rule

    # MONDO mapping + synonyms from the global index (if present; never required)
    idx = read_json(GLOBAL_INDEX, None)
    by_native = {}
    if idx:
        F = {k: i for i, k in enumerate(idx["f"])}
        for r in idx["rows"]:
            rec = {"mondo": r[F["id"]] if str(r[F["id"]]).startswith("MONDO:") else None,
                   "label": r[F["name"]], "syn": r[F["syn"]] or []}
            for o in filter(None, str(r[F["omim"]]).split(",")):
                by_native.setdefault(f"OMIM:{o}", rec)
            for o in filter(None, str(r[F["orpha"]]).split(",")):
                by_native.setdefault(f"ORPHA:{o}", rec)
    for did, d in diseases.items():
        m = by_native.get(did)
        d["mondo"] = m["mondo"] if m else None
        syn = []
        if m:
            if m["label"] and m["label"].lower() != d["name"].lower():
                syn.append(m["label"])
            syn += [s for s in m["syn"] if s and s.lower() != d["name"].lower()]
        if did.startswith("ORPHA:") and p6names.get(did) and p6names[did].lower() != d["name"].lower():
            syn.append(p6names[did])
        d["synonyms"] = sorted(set(syn), key=str.lower)
        d["n_hpo"] = n_hpo.get(did, 0)
        if not d["name"]:
            d["name"] = (m or {}).get("label") or did

    # somatic CANCER entries (e.g. 'Esophageal cancer, somatic') are not Mendelian diseases; somatic MOSAIC
    # disorders (Proteus, Sturge-Weber, MCAP ...) are kept
    ONCO = re.compile(r"cancer|carcinoma|tumou?r|neoplas|leuka?emia|lymphoma|melanoma|sarcoma|glioma|blastoma|"
                      r"myeloma|adenoma|pilomatrixoma|mesothelioma|seminoma", re.I)
    somatic_cancer = [k for k, d in diseases.items() if "somatic" in d["name"].lower() and ONCO.search(d["name"])]
    for k in somatic_cancer:
        del diseases[k]
    dropped["somatic cancer entries (diseases)"] = len(somatic_cancer)

    genes = collections.defaultdict(list)
    for did, d in diseases.items():
        for g in d["genes"]:
            genes[g].append(did)

    out = {
        "meta": {
            "generated": today(),
            "rules": {
                "OMIM": "genes_to_disease.txt association_type == MENDELIAN",
                "ORPHA": "Orphanet product6 association type 'Disease-causing germline mutation(s) ...' and status Assessed",
            },
            "sources": {
                "genes_to_disease.txt": "https://hpo.jax.org/data/annotations",
                "phenotype.hpoa": "https://hpo.jax.org/data/annotations",
                "en_product6.xml": P6_URL,
                "global_index": "data/derived/global/index.json" if idx else None,
            },
            "counts": {"diseases": len(diseases),
                       "omim": sum(1 for k in diseases if k.startswith("OMIM:")),
                       "orpha": sum(1 for k in diseases if k.startswith("ORPHA:")),
                       "genes": len(genes),
                       "with_mondo": sum(1 for d in diseases.values() if d["mondo"])},
            "dropped_rows": dict(dropped.most_common()),
        },
        "diseases": diseases,
        "genes": {g: sorted(v) for g, v in sorted(genes.items())},
    }
    write_json(OUT / "universe.json", out)
    print(out["meta"]["counts"])
    for k, v in list(dropped.most_common())[:12]:
        print("  dropped", v, k)


if __name__ == "__main__":
    main()
