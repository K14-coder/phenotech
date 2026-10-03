"""Task 2: gene -> Mendelian disease entities (Monarch v3, MONDO via OLS4, Open Targets).

Run:  python3 pipeline/biology/fetch_diseases.py [--refresh]
Needs: data/raw/biology/genes.json (from fetch_genes.py)
Out:  data/raw/biology/monarch/*.json, ols4/*.json, opentargets/*.json
      data/raw/biology/diseases.json  (normalised per-gene disease entities + inclusion decision)

Inclusion rule for EXTENDED genes: keep a gene only if at least one Mendelian
association is established in OMIM (Monarch causal edge), Orphanet (Monarch
hpoa gene-to-disease edge), Gene2Phenotype (confidence definitive/strong/moderate)
or ClinGen (Definitive/Strong/Moderate). Core and bridge genes are always kept.
"""
from __future__ import annotations

import json
import sys

from common import (ALL_GENES, BRIDGE_GENES, CORE_GENES, RAW, cached_json, read_json,
                    write_json)

REFRESH = "--refresh" in sys.argv
MONARCH = "https://api-v3.monarchinitiative.org/v3/api"
OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
OT_SOURCES = ["gene2phenotype", "clingen", "orphanet", "genomics_england", "uniprot_literature",
              "uniprot_variants", "eva"]
ESTABLISHED_G2P = {"definitive", "strong", "moderate"}
ESTABLISHED_CLINGEN = {"definitive", "strong", "moderate"}


def monarch_assocs(hgnc_id: str, category: str) -> list[dict]:
    obj = cached_json(RAW / "monarch" / f"{hgnc_id.replace(':', '_')}__{category.split(':')[1]}.json",
                      f"{MONARCH}/association",
                      params={"subject": hgnc_id, "category": category, "limit": 100},
                      refresh=REFRESH)
    return obj.get("items", [])


def monarch_entity(curie: str) -> dict:
    return cached_json(RAW / "monarch" / f"entity_{curie.replace(':', '_')}.json",
                       f"{MONARCH}/entity/{curie}", refresh=REFRESH)


def ols4_mondo(curie: str) -> dict | None:
    obj = cached_json(RAW / "ols4" / f"{curie.replace(':', '_')}.json",
                      "https://www.ebi.ac.uk/ols4/api/ontologies/mondo/terms",
                      params={"obo_id": curie}, refresh=REFRESH)
    terms = obj.get("_embedded", {}).get("terms", [])
    return terms[0] if terms else None


def ot_query(cache_name: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    return cached_json(RAW / "opentargets" / cache_name, OT_GQL,
                       headers={"Content-Type": "application/json"}, data=payload,
                       refresh=REFRESH)


OT_ASSOC_Q = """
query($ensg: String!) {
  target(ensemblId: $ensg) {
    id approvedSymbol
    associatedDiseases(page: {index: 0, size: 200}) {
      count
      rows { disease { id name } score datasourceScores { id score } }
    }
  }
}"""

OT_EVID_Q = """
query($ensg: String!, $efos: [String!]!, $ds: [String!]!) {
  target(ensemblId: $ensg) {
    evidences(efoIds: $efos, datasourceIds: $ds, size: 500) {
      count
      rows { datasourceId disease { id name } diseaseFromSource diseaseFromSourceMappedId
             confidence allelicRequirements studyId literature urls { niceName url } }
    }
  }
}"""


def orphadata(orpha: str) -> dict | None:
    """Orphanet gene-disease association record (association TYPE + validating PMIDs)."""
    try:
        obj = cached_json(RAW / "orphadata" / f"ORPHA_{orpha}.json",
                          f"https://api.orphadata.com/rd-associated-genes/orphacodes/{orpha}",
                          refresh=REFRESH)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! Orphadata failed for {orpha}: {ex}")
        return None
    res = (obj.get("data") or {}).get("results")
    return res if isinstance(res, dict) else None


def genes_to_disease() -> dict[str, list[dict]]:
    """HPO genes_to_disease.txt (OMIM via mim2gene_medgen, Orphanet via en_product6)."""
    from common import DOWNLOADS
    path = DOWNLOADS / "genes_to_disease.txt"
    if not path.exists():
        from common import http_get
        path.write_bytes(http_get("https://github.com/obophenotype/human-phenotype-ontology/"
                                  "releases/latest/download/genes_to_disease.txt"))
    out: dict[str, list[dict]] = {}
    for line in path.read_text().splitlines()[1:]:
        ncbi, sym, atype, did, src = line.split("\t")
        out.setdefault(sym, []).append({"association_type": atype, "disease_id": did, "source": src})
    return out


def classify_orpha(sym: str, orpha: str) -> dict:
    rec = orphadata(orpha)
    if not rec:
        return {"orpha": orpha, "found": False}
    assoc = rec.get("DisorderGeneAssociation") or []
    mine = [a for a in assoc if (a.get("Gene") or {}).get("Symbol") == sym]
    atype = mine[0].get("DisorderGeneAssociationType") if mine else None
    pmids = []
    if mine and mine[0].get("SourceOfValidation"):
        pmids = [p.replace("[PMID]", "") for p in mine[0]["SourceOfValidation"].split("_") if "PMID" in p]
    return {"orpha": orpha, "found": True, "name": rec.get("Preferred term"),
            "association_type": atype, "validation_pmids": pmids,
            "n_genes_associated": len(assoc),
            "causal": bool(atype and atype.startswith("Disease-causing")),
            "url": f"https://www.orpha.net/en/disease/detail/{orpha}"}


def main() -> None:
    genes = read_json(RAW / "genes.json")
    g2d = genes_to_disease()
    out = {}
    for sym in ALL_GENES:
        g = genes[sym]
        hid = g["hgnc_id"]
        print(f"[diseases] {sym} ({hid})")
        causal = monarch_assocs(hid, "biolink:CausalGeneToDiseaseAssociation")
        correl = monarch_assocs(hid, "biolink:CorrelatedGeneToDiseaseAssociation")
        ents: dict[str, dict] = {}
        for it in causal + correl:
            mondo = it["object"]
            e = ents.setdefault(mondo, {"mondo": mondo, "label": it.get("object_label"),
                                        "monarch_edges": []})
            e["monarch_edges"].append({
                "predicate": it.get("predicate"),
                "category": it.get("category"),
                "primary_knowledge_source": it.get("primary_knowledge_source"),
                "provided_by": it.get("provided_by"),
                "original_subject": it.get("original_subject"),
                "original_object": it.get("original_object"),
                "publications": it.get("publications"),
            })
        # entity details
        for mondo, e in ents.items():
            ent = monarch_entity(mondo)
            ols = ols4_mondo(mondo)
            xrefs = ent.get("xref") or []
            e.update({
                "name": ent.get("name"),
                "synonyms": ent.get("synonym") or [],
                "xrefs": xrefs,
                "omim": [x.split(":")[1] for x in xrefs if x.startswith("OMIM:")],
                "orpha": [x.split(":")[1] for x in xrefs if x.startswith("Orphanet:")],
                "inheritance": (ent.get("inheritance") or {}).get("name"),
                "inheritance_hpo": (ent.get("inheritance") or {}).get("id"),
                "description": ent.get("description"),
                "subsets": ent.get("subsets") or [],
                "ols4_label": ols.get("label") if ols else None,
                "ols4_iri": ols.get("iri") if ols else None,
            })
            # original OMIM/Orphanet ids from the edges themselves (authoritative for the link)
            e["omim_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                           if (m.get("original_object") or "").startswith("OMIM:")})
            e["orpha_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                            if (m.get("original_object") or "").startswith("Orphanet:")})
        # Open Targets
        ot = {"associated": [], "evidence": []}
        try:
            a = ot_query(f"{sym}_assoc.json", OT_ASSOC_Q, {"ensg": g["ensembl_gene_id"]})
            rows = a["data"]["target"]["associatedDiseases"]["rows"]
            keep = []
            for r in rows:
                ds = {d["id"]: d["score"] for d in r["datasourceScores"]}
                if any(ds.get(s, 0) > 0 for s in OT_SOURCES[:4]):
                    keep.append({"efo": r["disease"]["id"], "name": r["disease"]["name"],
                                 "score": r["score"], "datasources": ds})
            ot["associated"] = keep
            efos = [k["efo"] for k in keep]
            if efos:
                ev = ot_query(f"{sym}_evidence.json", OT_EVID_Q,
                              {"ensg": g["ensembl_gene_id"], "efos": efos, "ds": OT_SOURCES[:4]})
                ot["evidence"] = ev["data"]["target"]["evidences"]["rows"]
        except Exception as ex:  # noqa: BLE001
            print(f"  ! Open Targets failed for {sym}: {ex}")
        # Orphanet association types for every ORPHA code linked to this gene
        orpha_codes = set()
        for e in ents.values():
            orpha_codes.update(e["orpha_from_edges"])
        for row in g2d.get(sym, []):
            if row["disease_id"].startswith("ORPHA:"):
                orpha_codes.add(row["disease_id"].split(":")[1])
        orpha_assoc = {c: classify_orpha(sym, c) for c in sorted(orpha_codes)}
        for c, a in orpha_assoc.items():
            if a.get("found"):
                print(f"   ORPHA:{c} {a['name']!r} :: {a['association_type']} "
                      f"(genes={a['n_genes_associated']}, pmids={a['validation_pmids']})")
        # inclusion decision
        omim_causal = any(m["primary_knowledge_source"] == "infores:omim"
                          for e in ents.values() for m in e["monarch_edges"])
        orpha = any(a.get("causal") for a in orpha_assoc.values())
        g2p = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"]
                      if r["datasourceId"] == "gene2phenotype"})
        clingen = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"]
                          if r["datasourceId"] == "clingen"})
        established = (omim_causal or orpha or bool(ESTABLISHED_G2P & set(g2p))
                       or bool(ESTABLISHED_CLINGEN & set(clingen)))
        tier = "core" if sym in CORE_GENES else "bridge" if sym in BRIDGE_GENES else "extended"
        out[sym] = {
            "symbol": sym, "tier": tier,
            "include": True if tier != "extended" else established,
            "established_by": {"omim_causal": omim_causal, "orphanet_disease_causing": orpha,
                               "g2p_confidence": g2p, "clingen_classification": clingen},
            "entities": list(ents.values()),
            "orphanet_associations": orpha_assoc,
            "hpo_genes_to_disease": g2d.get(sym, []),
            "opentargets": ot,
        }
        for e in ents.values():
            srcs = sorted({m['primary_knowledge_source'] for m in e['monarch_edges']})
            print(f"   {e['mondo']} {e['name']!r} OMIM={e['omim']} ORPHA={e['orpha']} "
                  f"inh={e['inheritance']} src={srcs}")
        print(f"   G2P={g2p} ClinGen={clingen} include={out[sym]['include']}")
    write_json(RAW / "diseases.json", out)
    print(f"wrote {RAW / 'diseases.json'}")


if __name__ == "__main__":
    main()
