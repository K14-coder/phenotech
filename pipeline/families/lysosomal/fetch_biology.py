"""Genes and gene->disease entities for the lysosomal family.

Adapted from pipeline/biology/fetch_genes.py + fetch_diseases.py (same sources, same rules):
  HGNC REST, UniProt REST, Ensembl REST (MANE Select CDS length), Monarch v3 (OMIM causal edges),
  Orphadata (association TYPE, so susceptibility / modifier links are not counted as causal),
  Open Targets GraphQL (Gene2Phenotype + ClinGen validity).
Run:  python3 pipeline/families/lysosomal/fetch_biology.py [--refresh]
Out:  data/raw/families/lysosomal/{hgnc,uniprot,ensembl,monarch,orphadata,opentargets}/...
      data/raw/families/lysosomal/genes.json, diseases.json
"""
from __future__ import annotations

import json
import sys

from lyso_common import DOWNLOADS, GENES, RAW, cached_json, http_get, read_json, write_json

REFRESH = "--refresh" in sys.argv
MONARCH = "https://api-v3.monarchinitiative.org/v3/api"
OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
OT_SOURCES = ["gene2phenotype", "clingen", "orphanet", "genomics_england"]

PROTEIN_SYNONYMS = {
    "GBA1": ["glucocerebrosidase", "GCase", "acid beta-glucosidase", "GBA"],
    "GAA": ["acid alpha-glucosidase", "acid maltase"],
    "GLA": ["alpha-galactosidase A", "alpha-Gal A"],
    "HEXA": ["beta-hexosaminidase subunit alpha", "hexosaminidase A", "Hex A"],
    "NPC1": ["NPC intracellular cholesterol transporter 1", "Niemann-Pick C1 protein"],
    "SMPD1": ["acid sphingomyelinase", "ASM"],
    "IDUA": ["alpha-L-iduronidase"],
    "IDS": ["iduronate 2-sulfatase", "I2S"],
    "CLN3": ["battenin", "CLN3 lysosomal/endosomal transmembrane protein"],
    "TPP1": ["tripeptidyl peptidase 1", "TPP-1 (CLN2 protein)", "CLN2"],
    "ARSA": ["arylsulfatase A", "ASA"],
    "GALC": ["galactosylceramidase", "galactocerebrosidase"],
}


# ------------------------------------------------------------------ genes
def hgnc(symbol: str) -> dict:
    obj = cached_json(RAW / "hgnc" / f"{symbol}.json", f"https://rest.genenames.org/fetch/symbol/{symbol}",
                      headers={"Accept": "application/json"}, refresh=REFRESH)
    docs = obj["response"]["docs"]
    assert len(docs) == 1, f"HGNC returned {len(docs)} docs for {symbol}"
    return docs[0]


def uniprot(symbol: str) -> dict | None:
    obj = cached_json(RAW / "uniprot" / f"{symbol}.json", "https://rest.uniprot.org/uniprotkb/search",
                      params={"query": f"gene_exact:{symbol} AND organism_id:9606 AND reviewed:true",
                              "format": "json"}, refresh=REFRESH)
    res = obj.get("results", [])
    # gene_exact also matches aliases (e.g. "GLA" is an alias of NAT8, "ARSA" of GET3): require the
    # entry's PRIMARY gene name to be the HGNC symbol.
    primary = [r for r in res if any((g.get("geneName") or {}).get("value") == symbol for g in r.get("genes", []))]
    if not primary:
        print(f"  ! no UniProt entry with primary gene name {symbol} (results: "
              f"{[r['primaryAccession'] for r in res]})")
        return None
    return primary[0]


def ensembl_cds(enst: str) -> dict | None:
    enst = enst.split(".")[0]
    try:
        return cached_json(RAW / "ensembl" / f"{enst}.cds.json", f"https://rest.ensembl.org/sequence/id/{enst}",
                           params={"type": "cds"}, headers={"Content-Type": "application/json",
                                                            "Accept": "application/json"}, refresh=REFRESH)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Ensembl CDS fetch failed for {enst}: {e}")
        return None


def uniprot_function(entry: dict) -> str | None:
    for c in entry.get("comments", []):
        if c.get("commentType") == "FUNCTION":
            texts = c.get("texts", [])
            if texts:
                return texts[0]["value"]
    return None


def uniprot_names(entry: dict):
    pd = entry.get("proteinDescription", {})
    rec = pd.get("recommendedName", {}).get("fullName", {}).get("value")
    alts = []
    for a in pd.get("alternativeNames", []) or []:
        v = a.get("fullName", {}).get("value")
        if v:
            alts.append(v)
        for s in a.get("shortNames", []) or []:
            alts.append(s.get("value"))
    for s in pd.get("recommendedName", {}).get("shortNames", []) or []:
        alts.append(s.get("value"))
    return rec, [x for x in alts if x]


def subcellular(entry: dict) -> list[str]:
    out = []
    for c in entry.get("comments", []):
        if c.get("commentType") == "SUBCELLULAR LOCATION":
            for loc in c.get("subcellularLocations", []) or []:
                v = (loc.get("location") or {}).get("value")
                if v:
                    out.append(v)
    return sorted(set(out))


# ------------------------------------------------------------------ diseases
def monarch_assocs(hgnc_id: str, category: str) -> list[dict]:
    obj = cached_json(RAW / "monarch" / f"{hgnc_id.replace(':', '_')}__{category.split(':')[1]}.json",
                      f"{MONARCH}/association", params={"subject": hgnc_id, "category": category, "limit": 100},
                      refresh=REFRESH)
    return obj.get("items", [])


def monarch_entity(curie: str) -> dict:
    return cached_json(RAW / "monarch" / f"entity_{curie.replace(':', '_')}.json", f"{MONARCH}/entity/{curie}",
                       refresh=REFRESH)


def ot_query(cache_name: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    return cached_json(RAW / "opentargets" / cache_name, OT_GQL, headers={"Content-Type": "application/json"},
                       data=payload, refresh=REFRESH)


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
    try:
        obj = cached_json(RAW / "orphadata" / f"ORPHA_{orpha}.json",
                          f"https://api.orphadata.com/rd-associated-genes/orphacodes/{orpha}", refresh=REFRESH)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! Orphadata failed for {orpha}: {ex}")
        return None
    res = (obj.get("data") or {}).get("results")
    return res if isinstance(res, dict) else None


def genes_to_disease() -> dict:
    path = DOWNLOADS / "genes_to_disease.txt"
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
    return {"orpha": orpha, "found": True, "name": rec.get("Preferred term"), "association_type": atype,
            "validation_pmids": pmids, "n_genes_associated": len(assoc),
            "causal": bool(atype and atype.startswith("Disease-causing")),
            "url": f"https://www.orpha.net/en/disease/detail/{orpha}"}


def main() -> None:
    genes, diseases = {}, {}
    g2d = genes_to_disease()
    for sym in GENES:
        h = hgnc(sym)
        u = uniprot(sym)
        rec = {"symbol": h["symbol"], "hgnc_id": h["hgnc_id"], "name": h["name"],
               "alias_symbol": h.get("alias_symbol", []), "prev_symbol": h.get("prev_symbol", []),
               "entrez_id": h.get("entrez_id"), "omim_id": h.get("omim_id", []),
               "ensembl_gene_id": h.get("ensembl_gene_id"), "mane_select": h.get("mane_select", []),
               "location": h.get("location"),
               "hgnc_url": f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{h['hgnc_id']}"}
        if u:
            rn, alts = uniprot_names(u)
            rec.update({"uniprot_acc": u["primaryAccession"], "uniprot_entry": u.get("uniProtkbId"),
                        "protein_name": rn, "protein_alt_names": alts,
                        "protein_length_aa": u.get("sequence", {}).get("length"),
                        "uniprot_function": uniprot_function(u), "subcellular_location": subcellular(u),
                        "uniprot_url": f"https://www.uniprot.org/uniprotkb/{u['primaryAccession']}/entry"})
        enst = next((m for m in rec["mane_select"] if m.startswith("ENST")), None)
        if enst:
            cds = ensembl_cds(enst)
            if cds and cds.get("seq"):
                rec["mane_enst"] = enst
                rec["cds_length_bp"] = len(cds["seq"])
                rec["ensembl_cds_url"] = f"https://rest.ensembl.org/sequence/id/{enst.split('.')[0]}?type=cds"
        rec["protein_synonyms_curated"] = PROTEIN_SYNONYMS.get(sym, [])
        genes[sym] = rec
        print(f"[gene] {sym} {rec['hgnc_id']} OMIM={rec['omim_id']} aa={rec.get('protein_length_aa')} "
              f"cds={rec.get('cds_length_bp')} acc={rec.get('uniprot_acc')} loc={rec.get('subcellular_location')}")

        # ---- diseases
        hid = rec["hgnc_id"]
        causal = monarch_assocs(hid, "biolink:CausalGeneToDiseaseAssociation")
        correl = monarch_assocs(hid, "biolink:CorrelatedGeneToDiseaseAssociation")
        ents: dict[str, dict] = {}
        for it in causal + correl:
            mondo = it["object"]
            e = ents.setdefault(mondo, {"mondo": mondo, "label": it.get("object_label"), "monarch_edges": []})
            e["monarch_edges"].append({"predicate": it.get("predicate"), "category": it.get("category"),
                                       "primary_knowledge_source": it.get("primary_knowledge_source"),
                                       "original_object": it.get("original_object"),
                                       "publications": it.get("publications")})
        for mondo, e in ents.items():
            ent = monarch_entity(mondo)
            xrefs = ent.get("xref") or []
            e.update({"name": ent.get("name"), "synonyms": ent.get("synonym") or [], "xrefs": xrefs,
                      "omim": [x.split(":")[1] for x in xrefs if x.startswith("OMIM:")],
                      "orpha": [x.split(":")[1] for x in xrefs if x.startswith("Orphanet:")],
                      "inheritance": (ent.get("inheritance") or {}).get("name"),
                      "description": ent.get("description")})
            e["omim_from_edges"] = sorted({m["original_object"].split(":")[1] for m in e["monarch_edges"]
                                           if (m.get("original_object") or "").startswith("OMIM:")
                                           and m["predicate"] == "biolink:causes"})
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
            efos = [k["efo"] for k in keep]
            if efos:
                ev = ot_query(f"{sym}_evidence.json", OT_EVID_Q,
                              {"ensg": rec["ensembl_gene_id"], "efos": efos, "ds": OT_SOURCES})
                ot["evidence"] = ev["data"]["target"]["evidences"]["rows"]
        except Exception as ex:  # noqa: BLE001
            print(f"  ! Open Targets failed for {sym}: {ex}")
        orpha_codes = set()
        for e in ents.values():
            orpha_codes.update(e["orpha_from_edges"])
        for row in g2d.get(sym, []):
            if row["disease_id"].startswith("ORPHA:"):
                orpha_codes.add(row["disease_id"].split(":")[1])
        orpha_assoc = {c: classify_orpha(sym, c) for c in sorted(orpha_codes)}
        g2p = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"] if r["datasourceId"] == "gene2phenotype"})
        clingen = sorted({(r.get("confidence") or "").lower() for r in ot["evidence"] if r["datasourceId"] == "clingen"})
        diseases[sym] = {"symbol": sym, "entities": list(ents.values()), "orphanet_associations": orpha_assoc,
                         "hpo_genes_to_disease": g2d.get(sym, []), "opentargets": ot,
                         "established_by": {"omim_causal": any(m["primary_knowledge_source"] == "infores:omim"
                                                               and m["predicate"] == "biolink:causes"
                                                               for e in ents.values() for m in e["monarch_edges"]),
                                            "orphanet_disease_causing": any(a.get("causal") for a in orpha_assoc.values()),
                                            "g2p_confidence": g2p, "clingen_classification": clingen}}
        for e in ents.values():
            preds = sorted({(m["predicate"], m["primary_knowledge_source"]) for m in e["monarch_edges"]})
            print(f"   {e['mondo']} {e['name']!r} OMIM={e['omim_from_edges']} inh={e['inheritance']} {preds}")
        for c, a in orpha_assoc.items():
            if a.get("found"):
                print(f"   ORPHA:{c} {a['name']!r} :: {a['association_type']} (genes={a['n_genes_associated']})")
        print(f"   G2P={g2p} ClinGen={clingen}")
    write_json(RAW / "genes.json", genes)
    write_json(RAW / "diseases.json", diseases)
    print("wrote genes.json, diseases.json")


if __name__ == "__main__":
    main()
