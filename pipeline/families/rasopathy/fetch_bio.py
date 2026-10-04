"""Gene + disease records for the RASopathy family (adapted from pipeline/biology/fetch_genes.py
and fetch_diseases.py).

Run:  python3 pipeline/families/rasopathy/fetch_bio.py [--refresh]
Out:  data/raw/families/rasopathy/{hgnc,uniprot,ensembl,monarch,orphadata,opentargets}/...
      data/raw/families/rasopathy/genes.json, diseases.json
Sources: HGNC REST, UniProt REST, Ensembl REST (MANE Select CDS), Monarch v3 API
(CausalGeneToDiseaseAssociation = OMIM/Orphanet causal edges), Orphadata
rd-associated-genes (association TYPE), Open Targets GraphQL (Gene2Phenotype / ClinGen /
Orphanet / Genomics England evidence), HPO genes_to_disease.txt.
"""
from __future__ import annotations

import json
import sys

from ras_common import DOWNLOADS, GENES, RAW, cached_json, http_get, write_json

REFRESH = "--refresh" in sys.argv
MONARCH = "https://api-v3.monarchinitiative.org/v3/api"
OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
OT_SOURCES = ["gene2phenotype", "clingen", "orphanet", "genomics_england"]

PROTEIN_SYNONYMS = {
    "PTPN11": ["SHP2", "SHP-2", "PTP2C"],
    "SOS1": ["Son of sevenless homolog 1"],
    "RAF1": ["CRAF", "C-RAF", "c-Raf-1"],
    "BRAF": ["B-Raf", "BRAF1"],
    "KRAS": ["K-Ras", "KRAS2"],
    "HRAS": ["H-Ras", "c-H-ras"],
    "NF1": ["neurofibromin"],
    "MAP2K1": ["MEK1", "MKK1"],
    "SHOC2": ["SUR-8", "SOC-2 homolog"],
    "CBL": ["c-Cbl", "CBL2", "RNF55"],
    "RIT1": ["RIT", "RIBB", "ROC1"],
    "LZTR1": ["LZTR-1"],
}


def hgnc(sym):
    obj = cached_json(RAW / "hgnc" / f"{sym}.json", f"https://rest.genenames.org/fetch/symbol/{sym}",
                      headers={"Accept": "application/json"}, refresh=REFRESH)
    docs = obj["response"]["docs"]
    assert len(docs) == 1, f"HGNC returned {len(docs)} docs for {sym}"
    return docs[0]


def uniprot(sym):
    obj = cached_json(RAW / "uniprot" / f"{sym}.json", "https://rest.uniprot.org/uniprotkb/search",
                      params={"query": f"gene_exact:{sym} AND organism_id:9606 AND reviewed:true",
                              "format": "json"}, refresh=REFRESH)
    res = obj.get("results", [])
    # gene_exact also matches aliases (e.g. "RIT1" is an alias of BCL11B): require the entry's PRIMARY gene name
    # to be the HGNC symbol.
    primary = [r for r in res if any((g.get("geneName") or {}).get("value") == sym for g in r.get("genes", []))]
    if not primary:
        print(f"  ! no UniProt entry with primary gene name {sym} (results: "
              f"{[r['primaryAccession'] for r in res]})")
        return None
    return primary[0]


def ensembl_cds(enst):
    enst = enst.split(".")[0]
    try:
        return cached_json(RAW / "ensembl" / f"{enst}.cds.json", f"https://rest.ensembl.org/sequence/id/{enst}",
                           params={"type": "cds"}, headers={"Content-Type": "application/json",
                                                            "Accept": "application/json"}, refresh=REFRESH)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Ensembl CDS failed for {enst}: {e}")
        return None


def uniprot_function(entry):
    for c in entry.get("comments", []):
        if c.get("commentType") == "FUNCTION" and c.get("texts"):
            return c["texts"][0]["value"]
    return None


def uniprot_names(entry):
    pd = entry.get("proteinDescription", {})
    rec = pd.get("recommendedName", {}).get("fullName", {}).get("value")
    alts = []
    for a in pd.get("alternativeNames", []) or []:
        if a.get("fullName", {}).get("value"):
            alts.append(a["fullName"]["value"])
        alts += [s.get("value") for s in a.get("shortNames", []) or []]
    alts += [s.get("value") for s in pd.get("recommendedName", {}).get("shortNames", []) or []]
    return rec, [x for x in alts if x]


def monarch_assocs(hid, category):
    obj = cached_json(RAW / "monarch" / f"{hid.replace(':', '_')}__{category.split(':')[1]}.json",
                      f"{MONARCH}/association", params={"subject": hid, "category": category, "limit": 200},
                      refresh=REFRESH)
    return obj.get("items", [])


def monarch_entity(curie):
    return cached_json(RAW / "monarch" / f"entity_{curie.replace(':', '_')}.json",
                       f"{MONARCH}/entity/{curie}", refresh=REFRESH)


def ot_query(name, query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode()
    return cached_json(RAW / "opentargets" / name, OT_GQL, headers={"Content-Type": "application/json"},
                       data=payload, refresh=REFRESH)


OT_ASSOC_Q = """query($ensg: String!) { target(ensemblId: $ensg) { id approvedSymbol
  associatedDiseases(page: {index: 0, size: 500}) { count
    rows { disease { id name } score datasourceScores { id score } } } } }"""
OT_EVID_Q = """query($ensg: String!, $efos: [String!]!, $ds: [String!]!) { target(ensemblId: $ensg) {
  evidences(efoIds: $efos, datasourceIds: $ds, size: 1000) { count
    rows { datasourceId disease { id name } diseaseFromSource diseaseFromSourceMappedId
           confidence allelicRequirements studyId literature urls { niceName url } } } } }"""


def orphadata(orpha):
    try:
        obj = cached_json(RAW / "orphadata" / f"ORPHA_{orpha}.json",
                          f"https://api.orphadata.com/rd-associated-genes/orphacodes/{orpha}", refresh=REFRESH)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! Orphadata failed for {orpha}: {ex}")
        return None
    res = (obj.get("data") or {}).get("results")
    return res if isinstance(res, dict) else None


def classify_orpha(sym, orpha):
    rec = orphadata(orpha)
    if not rec:
        return {"orpha": orpha, "found": False}
    assoc = rec.get("DisorderGeneAssociation") or []
    mine = [a for a in assoc if (a.get("Gene") or {}).get("Symbol") == sym]
    atype = mine[0].get("DisorderGeneAssociationType") if mine else None
    pmids = []
    if mine and mine[0].get("SourceOfValidation"):
        pmids = [p.replace("[PMID]", "") for p in mine[0]["SourceOfValidation"].split("_") if "PMID" in p]
    return {"orpha": orpha, "found": True, "name": rec.get("Preferred term"), "association_type": atype,
            "validation_pmids": pmids, "n_genes_associated": len(assoc),
            "genes_associated": sorted({(a.get("Gene") or {}).get("Symbol") for a in assoc} - {None}),
            "causal": bool(atype and atype.startswith("Disease-causing")),
            "url": f"https://www.orpha.net/en/disease/detail/{orpha}"}


def genes_to_disease():
    path = DOWNLOADS / "genes_to_disease.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(http_get("https://github.com/obophenotype/human-phenotype-ontology/"
                                  "releases/latest/download/genes_to_disease.txt"))
    out = {}
    for line in path.read_text().splitlines()[1:]:
        ncbi, sym, atype, did, src = line.split("\t")
        out.setdefault(sym, []).append({"association_type": atype, "disease_id": did, "source": src})
    return out


def main():
    g2d = genes_to_disease()
    genes, diseases = {}, {}
    for sym in GENES:
        h = hgnc(sym)
        u = uniprot(sym)
        rec = {"symbol": h["symbol"], "hgnc_id": h["hgnc_id"], "name": h["name"],
               "alias_symbol": h.get("alias_symbol", []), "prev_symbol": h.get("prev_symbol", []),
               "entrez_id": h.get("entrez_id"), "omim_id": h.get("omim_id", []),
               "ensembl_gene_id": h.get("ensembl_gene_id"), "uniprot_ids_hgnc": h.get("uniprot_ids", []),
               "mane_select": h.get("mane_select", []),
               "hgnc_url": f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{h['hgnc_id']}",
               "protein_synonyms_curated": PROTEIN_SYNONYMS.get(sym, [])}
        if u:
            name, alts = uniprot_names(u)
            rec.update({"uniprot_acc": u["primaryAccession"], "uniprot_entry": u.get("uniProtkbId"),
                        "protein_name": name, "protein_alt_names": alts,
                        "protein_length_aa": u.get("sequence", {}).get("length"),
                        "uniprot_function": uniprot_function(u),
                        "uniprot_url": f"https://www.uniprot.org/uniprotkb/{u['primaryAccession']}/entry"})
        enst = next((m for m in rec["mane_select"] if m.startswith("ENST")), None)
        if enst:
            cds = ensembl_cds(enst)
            if cds and cds.get("seq"):
                rec["mane_enst"] = enst
                rec["cds_length_bp"] = len(cds["seq"])
                rec["ensembl_cds_url"] = f"https://rest.ensembl.org/sequence/id/{enst.split('.')[0]}?type=cds"
        genes[sym] = rec
        print(f"[gene] {sym} {rec['hgnc_id']} OMIM={rec['omim_id']} {rec.get('uniprot_acc')} "
              f"aa={rec.get('protein_length_aa')} cds={rec.get('cds_length_bp')}")

        # ---- diseases
        hid = rec["hgnc_id"]
        causal = monarch_assocs(hid, "biolink:CausalGeneToDiseaseAssociation")
        correl = monarch_assocs(hid, "biolink:CorrelatedGeneToDiseaseAssociation")
        ents = {}
        for it in causal + correl:
            e = ents.setdefault(it["object"], {"mondo": it["object"], "label": it.get("object_label"),
                                               "monarch_edges": []})
            e["monarch_edges"].append({k: it.get(k) for k in (
                "predicate", "category", "primary_knowledge_source", "provided_by", "original_subject",
                "original_object", "publications")})
        for mondo, e in ents.items():
            ent = monarch_entity(mondo)
            xr = ent.get("xref") or []
            e.update({"name": ent.get("name"), "synonyms": ent.get("synonym") or [], "xrefs": xr,
                      "inheritance": (ent.get("inheritance") or {}).get("name"),
                      "description": ent.get("description")})
            e["omim_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                           if (m.get("original_object") or "").startswith("OMIM:")})
            e["orpha_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                            if (m.get("original_object") or "").startswith("Orphanet:")})
        ot = {"associated": [], "evidence": []}
        try:
            a = ot_query(f"{sym}_assoc.json", OT_ASSOC_Q, {"ensg": rec["ensembl_gene_id"]})
            rows = a["data"]["target"]["associatedDiseases"]["rows"]
            keep = []
            for r in rows:
                ds = {d["id"]: d["score"] for d in r["datasourceScores"]}
                if any(ds.get(s, 0) > 0 for s in OT_SOURCES):
                    keep.append({"efo": r["disease"]["id"], "name": r["disease"]["name"], "score": r["score"],
                                 "datasources": ds})
            ot["associated"] = keep
            if keep:
                ev = ot_query(f"{sym}_evidence.json", OT_EVID_Q, {"ensg": rec["ensembl_gene_id"],
                                                                 "efos": [k["efo"] for k in keep], "ds": OT_SOURCES})
                ot["evidence"] = ev["data"]["target"]["evidences"]["rows"]
        except Exception as ex:  # noqa: BLE001
            print(f"  ! Open Targets failed for {sym}: {ex}")
        codes = set()
        for e in ents.values():
            codes.update(e["orpha_from_edges"])
        for row in g2d.get(sym, []):
            if row["disease_id"].startswith("ORPHA:"):
                codes.add(row["disease_id"].split(":")[1])
        orpha_assoc = {c: classify_orpha(sym, c) for c in sorted(codes)}
        diseases[sym] = {"symbol": sym, "entities": list(ents.values()), "orphanet_associations": orpha_assoc,
                         "hpo_genes_to_disease": g2d.get(sym, []), "opentargets": ot}
        for e in ents.values():
            srcs = sorted({m["primary_knowledge_source"] for m in e["monarch_edges"]})
            print(f"   {e['mondo']} {e['name']!r} OMIM={e['omim_from_edges']} ORPHA={e['orpha_from_edges']} "
                  f"inh={e['inheritance']} src={srcs}")
        for c, a in orpha_assoc.items():
            if a.get("found"):
                print(f"   ORPHA:{c} {a['name']!r} :: {a['association_type']} (genes={a['n_genes_associated']})")
        g2p = sorted({(r.get('diseaseFromSource'), r.get('confidence')) for r in ot['evidence']
                      if r['datasourceId'] == 'gene2phenotype'})
        cg = sorted({(r.get('diseaseFromSource'), r.get('confidence')) for r in ot['evidence']
                     if r['datasourceId'] == 'clingen'})
        print(f"   G2P={g2p}\n   ClinGen={cg}")
    write_json(RAW / "genes.json", genes)
    write_json(RAW / "diseases.json", diseases)
    print("wrote genes.json, diseases.json")


if __name__ == "__main__":
    main()
