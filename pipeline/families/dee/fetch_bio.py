"""DEE family, step 1: gene records (HGNC, UniProt, Ensembl CDS) and gene -> Mendelian disease
entities (Monarch v3, MONDO via OLS4, Orphadata association types, Open Targets G2P/ClinGen).

Adapted from pipeline/biology/fetch_genes.py + fetch_diseases.py; raw responses are cached under
data/raw/families/dee/{hgnc,uniprot,ensembl,monarch,ols4,orphadata,opentargets}/.

Run:  python3 pipeline/families/dee/fetch_bio.py [--refresh]
Out:  data/raw/families/dee/genes.json, data/raw/families/dee/diseases.json
"""
from __future__ import annotations

import json
import sys

from dee_common import DOWNLOADS, GENES, RAW, cached_json, http_get, read_json, write_json

REFRESH = "--refresh" in sys.argv
MONARCH = "https://api-v3.monarchinitiative.org/v3/api"
OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
OT_SOURCES = ["gene2phenotype", "clingen", "orphanet", "genomics_england"]

PROTEIN_SYNONYMS = {
    "SCN1A": ["Nav1.1", "NaV1.1", "sodium channel alpha subunit 1"],
    "SCN2A": ["Nav1.2", "NaV1.2"],
    "SCN8A": ["Nav1.6", "NaV1.6"],
    "KCNQ2": ["Kv7.2", "KV7.2"],
    "KCNT1": ["KNa1.1", "Slack", "SLO2.2"],
    "CACNA1A": ["Cav2.1", "CaV2.1", "P/Q-type calcium channel alpha 1A"],
    "GRIN2B": ["GluN2B", "NR2B"],
    "CDKL5": ["STK9", "cyclin-dependent kinase-like 5"],
    "SYNGAP1": ["SynGAP", "synaptic Ras GTPase-activating protein 1"],
    "SLC2A1": ["GLUT1", "GLUT-1", "glucose transporter 1"],
}


# ------------------------------------------------------------------ genes
def hgnc(symbol):
    obj = cached_json(RAW / "hgnc" / f"{symbol}.json", f"https://rest.genenames.org/fetch/symbol/{symbol}",
                      headers={"Accept": "application/json"}, refresh=REFRESH)
    docs = obj["response"]["docs"]
    assert len(docs) == 1, f"HGNC returned {len(docs)} docs for {symbol}"
    return docs[0]


def uniprot(symbol):
    obj = cached_json(RAW / "uniprot" / f"{symbol}.json", "https://rest.uniprot.org/uniprotkb/search",
                      params={"query": f"gene_exact:{symbol} AND organism_id:9606 AND reviewed:true",
                              "format": "json"}, refresh=REFRESH)
    res = obj.get("results", [])
    return res[0] if res else None


def ensembl_cds(enst):
    enst = enst.split(".")[0]
    try:
        return cached_json(RAW / "ensembl" / f"{enst}.cds.json", f"https://rest.ensembl.org/sequence/id/{enst}",
                           params={"type": "cds"}, headers={"Content-Type": "application/json",
                                                            "Accept": "application/json"}, refresh=REFRESH)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Ensembl CDS fetch failed for {enst}: {e}")
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
        for s in a.get("shortNames", []) or []:
            alts.append(s.get("value"))
    for s in pd.get("recommendedName", {}).get("shortNames", []) or []:
        alts.append(s.get("value"))
    return rec, [x for x in alts if x]


def fetch_genes():
    out = {}
    for sym in GENES:
        h = hgnc(sym)
        u = uniprot(sym)
        rec = {"symbol": h["symbol"], "hgnc_id": h["hgnc_id"], "name": h["name"],
               "alias_symbol": h.get("alias_symbol", []), "prev_symbol": h.get("prev_symbol", []),
               "entrez_id": h.get("entrez_id"), "omim_id": h.get("omim_id", []),
               "ensembl_gene_id": h.get("ensembl_gene_id"), "uniprot_ids_hgnc": h.get("uniprot_ids", []),
               "mane_select": h.get("mane_select", []), "location": h.get("location"),
               "hgnc_url": f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{h['hgnc_id']}"}
        if u:
            rn, alts = uniprot_names(u)
            rec.update({"uniprot_acc": u["primaryAccession"], "uniprot_entry": u.get("uniProtkbId"),
                        "protein_name": rn, "protein_alt_names": alts,
                        "protein_length_aa": u.get("sequence", {}).get("length"),
                        "uniprot_function": uniprot_function(u),
                        "uniprot_url": f"https://www.uniprot.org/uniprotkb/{u['primaryAccession']}/entry"})
        enst = next((m for m in rec["mane_select"] if m.startswith("ENST")), None)
        if enst:
            cds = ensembl_cds(enst)
            if cds and cds.get("seq"):
                rec.update({"mane_enst": enst, "cds_length_bp": len(cds["seq"]),
                            "ensembl_cds_url": f"https://rest.ensembl.org/sequence/id/{enst.split('.')[0]}?type=cds"})
        rec["protein_synonyms_curated"] = PROTEIN_SYNONYMS.get(sym, [])
        out[sym] = rec
        print(f"[genes] {sym} {rec['hgnc_id']} OMIM={rec['omim_id']} aa={rec.get('protein_length_aa')} "
              f"cds={rec.get('cds_length_bp')} acc={rec.get('uniprot_acc')}")
    write_json(RAW / "genes.json", out)
    return out


# ------------------------------------------------------------------ diseases
def monarch_assocs(hgnc_id, category):
    obj = cached_json(RAW / "monarch" / f"{hgnc_id.replace(':', '_')}__{category.split(':')[1]}.json",
                      f"{MONARCH}/association", params={"subject": hgnc_id, "category": category, "limit": 100},
                      refresh=REFRESH)
    return obj.get("items", [])


def monarch_entity(curie):
    return cached_json(RAW / "monarch" / f"entity_{curie.replace(':', '_')}.json", f"{MONARCH}/entity/{curie}",
                       refresh=REFRESH)


def ols4_mondo(curie):
    obj = cached_json(RAW / "ols4" / f"{curie.replace(':', '_')}.json",
                      "https://www.ebi.ac.uk/ols4/api/ontologies/mondo/terms", params={"obo_id": curie},
                      refresh=REFRESH)
    t = obj.get("_embedded", {}).get("terms", [])
    return t[0] if t else None


def ot_query(cache_name, query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode()
    return cached_json(RAW / "opentargets" / cache_name, OT_GQL, headers={"Content-Type": "application/json"},
                       data=payload, refresh=REFRESH)


OT_ASSOC_Q = """
query($ensg: String!) { target(ensemblId: $ensg) { id approvedSymbol
  associatedDiseases(page: {index: 0, size: 200}) { count
    rows { disease { id name } score datasourceScores { id score } } } } }"""
OT_EVID_Q = """
query($ensg: String!, $efos: [String!]!, $ds: [String!]!) { target(ensemblId: $ensg) {
  evidences(efoIds: $efos, datasourceIds: $ds, size: 500) { count
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


def genes_to_disease():
    path = DOWNLOADS / "genes_to_disease.txt"
    if not path.exists():
        path.write_bytes(http_get("https://github.com/obophenotype/human-phenotype-ontology/"
                                  "releases/latest/download/genes_to_disease.txt"))
    out = {}
    for line in path.read_text().splitlines()[1:]:
        ncbi, sym, atype, did, src = line.split("\t")
        out.setdefault(sym, []).append({"association_type": atype, "disease_id": did, "source": src})
    return out


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
            "causal": bool(atype and atype.startswith("Disease-causing")),
            "url": f"https://www.orpha.net/en/disease/detail/{orpha}"}


def fetch_diseases(genes):
    g2d = genes_to_disease()
    out = {}
    for sym in GENES:
        g = genes[sym]
        hid = g["hgnc_id"]
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
            ols = ols4_mondo(mondo)
            xr = ent.get("xref") or []
            e.update({"name": ent.get("name"), "synonyms": ent.get("synonym") or [], "xrefs": xr,
                      "omim": [x.split(":")[1] for x in xr if x.startswith("OMIM:")],
                      "orpha": [x.split(":")[1] for x in xr if x.startswith("Orphanet:")],
                      "inheritance": (ent.get("inheritance") or {}).get("name"),
                      "description": ent.get("description"),
                      "ols4_label": ols.get("label") if ols else None})
            e["omim_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                           if (m.get("original_object") or "").startswith("OMIM:")})
            e["orpha_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                            if (m.get("original_object") or "").startswith("Orphanet:")})
        ot = {"associated": [], "evidence": []}
        try:
            a = ot_query(f"{sym}_assoc.json", OT_ASSOC_Q, {"ensg": g["ensembl_gene_id"]})
            keep = []
            for r in a["data"]["target"]["associatedDiseases"]["rows"]:
                ds = {d["id"]: d["score"] for d in r["datasourceScores"]}
                if any(ds.get(s, 0) > 0 for s in OT_SOURCES):
                    keep.append({"efo": r["disease"]["id"], "name": r["disease"]["name"], "score": r["score"],
                                 "datasources": ds})
            ot["associated"] = keep
            if keep:
                ev = ot_query(f"{sym}_evidence.json", OT_EVID_Q, {"ensg": g["ensembl_gene_id"],
                                                                  "efos": [k["efo"] for k in keep],
                                                                  "ds": OT_SOURCES})
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
        omim_causal = any(m["primary_knowledge_source"] == "infores:omim"
                          for e in ents.values() for m in e["monarch_edges"])
        g2p = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"]
                      if r["datasourceId"] == "gene2phenotype"})
        clingen = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"]
                          if r["datasourceId"] == "clingen"})
        out[sym] = {"symbol": sym, "tier": "core", "include": True,
                    "established_by": {"omim_causal": omim_causal,
                                       "orphanet_disease_causing": any(a.get("causal") for a in orpha_assoc.values()),
                                       "g2p_confidence": g2p, "clingen_classification": clingen},
                    "entities": list(ents.values()), "orphanet_associations": orpha_assoc,
                    "hpo_genes_to_disease": g2d.get(sym, []), "opentargets": ot}
        print(f"[diseases] {sym}: {len(ents)} MONDO entities, {len(orpha_assoc)} ORPHA codes, "
              f"G2P={g2p} ClinGen={clingen}")
        for e in ents.values():
            srcs = sorted({m['primary_knowledge_source'] for m in e['monarch_edges']})
            print(f"     {e['mondo']} {e['name']!r} OMIM={e['omim_from_edges']} ORPHA={e['orpha_from_edges']} {srcs}")
        for c, a in orpha_assoc.items():
            if a.get("found"):
                print(f"     ORPHA:{c} {a['name']!r} :: {a['association_type']} genes={a['n_genes_associated']}")
    write_json(RAW / "diseases.json", out)


if __name__ == "__main__":
    gs = fetch_genes() if (REFRESH or not (RAW / "genes.json").exists()) else read_json(RAW / "genes.json")
    fetch_diseases(gs)
