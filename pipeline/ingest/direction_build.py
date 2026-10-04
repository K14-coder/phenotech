"""Direction layer: which way a disease moves its gene's function, and which way a drug moves its target.

    curl -o data/raw/downloads/opentargets/drug_mechanism_of_action.parquet \
      https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/drug_mechanism_of_action/00000000.parquet
    curl -o data/raw/downloads/opentargets/drug_molecule.parquet \
      https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/drug_molecule/00000000.parquet
    uv run --with pyarrow --with pandas python3 pipeline/ingest/direction_build.py      # ~20 s, offline after download
    python3 pipeline/ingest/direction_build.py --curated-only   # no downloads: re-classify only the atlas'
                                                                # therapies, reusing the ChEMBL table already in drug_direction.json

Writes data/derived/direction/gene_direction.json and drug_direction.json (each with sources).

Disease side (per disease x gene): "LoF" = too little function (loss of function, haploinsufficiency,
dominant negative, destabilisation, deficiency); "GoF" = too much (gain of function, hyperactivation,
increased gene product level). Evidence is weighted and summed per source:
  * G2P (global/mechanism shards): mechanism class (weight 1.0; 0.6 when mechanism_support == "inferred"),
    plus variant_consequence "increased gene product level" -> GoF (0.6).
  * ClinGen dosage HI score 3 -> LoF (0.6).
  * DisMech (global/dismech shards): step labels that name a gene of the record, or steps with role "trigger",
    keyword-classified (regexes GOF_RE / LOF_RE below; weight 0.8 per step, max 2 steps counted per gene).
    The matched step label and keyword are kept as the basis.
  * Atlas graph (data/graph.json): driven_by and variant_group has_effect edges to the generic classes,
    weighted by evidence level (curated 1, experimental 0.8, observational 0.5, inferred 0.3).
  * gnomAD constraint (LOEUF < 0.35): weak LoF support (0.2). It never sets a direction on its own:
    a constraint-only call is labelled confidence "weak" and is ignored by the scorer by default.
Direction = the side with >= 2x the weight of the other (and >= 0.5 absolute); otherwise "mixed" (neutral).

Drug side: ChEMBL mechanism-of-action action types as redistributed by the Open Targets Platform
(drug_mechanism_of_action, drug_molecule parquet; ChEMBL CC BY-SA 3.0, Open Targets CC0). The ChEMBL REST
API returned HTTP 500 during this build, so the bulk Open Targets copy of the same ChEMBL table was used.
DrugBank ids come from drug_molecule.crossReferences (parents and salts merged). Ensembl -> HGNC symbol via
hgnc_complete_set.txt. Curated atlas therapies (graph therapy nodes) are classified from modality + summary.
"""
from __future__ import annotations

import csv
import json
import pathlib
import re
import sys
import time
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/downloads"
GLOB = ROOT / "data/derived/global"
OUTD = ROOT / "data/derived/direction"

DECREASE = {"INHIBITOR", "ANTAGONIST", "BLOCKER", "NEGATIVE ALLOSTERIC MODULATOR", "NEGATIVE MODULATOR",
            "ANTISENSE INHIBITOR", "RNAI INHIBITOR", "INVERSE AGONIST", "ALLOSTERIC ANTAGONIST", "DEGRADER",
            "DISRUPTING AGENT", "GENE EDITING NEGATIVE MODULATOR"}
INCREASE = {"AGONIST", "PARTIAL AGONIST", "ACTIVATOR", "OPENER", "POSITIVE ALLOSTERIC MODULATOR",
            "POSITIVE MODULATOR", "STABILISER", "EXOGENOUS PROTEIN", "EXOGENOUS GENE"}
# left neutral on purpose: MODULATOR, BINDING AGENT, OTHER, SUBSTRATE, CROSS-LINKING AGENT, VACCINE ANTIGEN,
# RELEASING AGENT, HYDROLYTIC ENZYME, PROTEOLYTIC ENZYME (the target of an enzyme drug is its substrate)

GOF_RE = re.compile(r"gain[- ]of[- ]function|\bgof\b|hyperactiv|over[- ]?activ|constitutive(ly)?[- ]activ|"
                    r"increased (channel |kinase |enzyme |catalytic )?(activity|function|current|conductance|signal\w*)|"
                    r"enhanced (channel |kinase )?(activity|function|current)|persistent (sodium )?current|"
                    r"toxic gain|increased gene product level|overexpression|excess(ive)? (activity|signal\w*)", re.I)
LOF_RE = re.compile(r"loss[- ]of[- ]function|\blof\b|haplo[- ]?insufficien|deficien|dominant[- ]negative|"
                    r"reduced|decreased|loss of|absent|absence of|impaired|null\b|truncat|destabili[sz]|"
                    r"misfold|degradation|hypomorph|insufficient", re.I)

LEVEL_W = {"curated": 1.0, "experimental": 0.8, "observational": 0.5, "inferred": 0.3}
CLASS_DIR = {"mech:loss-of-function": "LoF", "mech:haploinsufficiency": "LoF", "mech:dominant-negative": "LoF",
             "mech:protein-destabilization": "LoF", "mech:lysosomal-enzyme-deficiency": "LoF",
             "mech:gain-of-function": "GoF"}


def call(lof, gof, weak_lof=0.0):
    """weak_lof (gnomAD) adds to the ratio but never to the 0.5 evidence threshold."""
    if gof >= 0.5 and gof >= 2 * (lof + weak_lof):
        return "GoF"
    if lof >= 0.5 and lof + weak_lof >= 2 * gof:
        return "LoF"
    if lof + gof >= 0.5:
        return "mixed"
    return None


class Acc:
    def __init__(self):
        self.d = defaultdict(lambda: {"lof": 0.0, "gof": 0.0, "basis": []})

    def add(self, key, side, w, basis):
        r = self.d[key]
        r["lof" if side == "LoF" else "gof"] += w
        if basis.get("source") == "gnomAD v4.1":
            r["weak"] = r.get("weak", 0.0) + w
        if len(r["basis"]) < 8:
            r["basis"].append({**basis, "side": side, "w": round(w, 2)})


def disease_side(con):
    acc = Acc()               # key (MONDO, gene)
    n_g2p = n_dm = 0
    for b in range(64):
        d = json.load(open(GLOB / "mechanism" / f"{b}.json"))["d"]
        for mondo, v in d.items():
            for r in v.get("mechanisms", []):
                g = r.get("gene")
                if not g:
                    continue
                side = CLASS_DIR.get(r.get("class") or "")
                vc = (r.get("variant_consequence") or "")
                if r["source"] == "G2P":
                    if side:
                        w = 0.6 if r.get("mechanism_support") == "inferred" else 1.0
                        acc.add((mondo, g), side, w, {"source": "G2P", "label": r.get("label_verbatim"),
                                                      "ref": r.get("record"), "url": r.get("url")})
                        n_g2p += 1
                    if "increased gene product level" in vc:
                        acc.add((mondo, g), "GoF", 0.6, {"source": "G2P", "label": vc, "ref": r.get("record"),
                                                         "url": r.get("url")})
                elif r["source"] == "ClinGen dosage" and side:
                    # a gene-level HI score copied onto every dominant entry of the gene says little about a
                    # GoF allelic disorder of the same gene (SCN2A, SCN8A), so it counts less there
                    gl = "gene-level" in (r.get("joined_by") or "")
                    acc.add((mondo, g), side, 0.4 if gl else 0.6,
                            {"source": "ClinGen dosage", "label": r.get("label_verbatim"), "url": r.get("url"),
                             "joined_by": r.get("joined_by")})
    # DisMech
    for b in range(64):
        sh = json.load(open(GLOB / "dismech" / f"{b}.json"))
        for mondo, recs in sh["d"].items():
            for rec in recs:
                genes = sorted({s["gene_ref"] for s in rec.get("steps", []) if s.get("gene_ref")})
                if not genes:
                    continue
                cnt = defaultdict(int)
                for s in rec["steps"]:
                    if s.get("sec") != "pathophysiology":
                        continue
                    lab = s.get("label") or ""
                    named = [g for g in genes if re.search(r"(?<![A-Za-z0-9])" + re.escape(g) + r"(?![A-Za-z0-9])", lab)]
                    if not named and s.get("role") == "trigger":
                        named = genes if len(genes) <= 2 else []
                    if not named:
                        continue
                    mg, ml = GOF_RE.search(lab), LOF_RE.search(lab)
                    for g in named:
                        for side, m in (("GoF", mg), ("LoF", ml)):
                            if m and cnt[(g, side)] < 2:
                                cnt[(g, side)] += 1
                                acc.add((mondo, g), side, 0.8, {"source": "DisMech", "label": lab,
                                                                "keyword": m.group(0), "ref": rec.get("file")})
                                n_dm += 1
    # gnomAD weak support
    for (mondo, g), r in list(acc.d.items()):
        c = con.get(g)
        if c and c[1] is not None and c[1] < 0.35:
            acc.add((mondo, g), "LoF", 0.2, {"source": "gnomAD v4.1", "label": f"LOEUF {c[1]:.2f} < 0.35 (weak)"})
    return acc, n_g2p, n_dm


def graph_side(graph):
    acc = Acc()
    by = defaultdict(list)
    for e in graph["edges"]:
        if e.get("evidence_level") != "hypothesis":
            by[e["type"]].append(e)
    gene_of = {e["target"]: e["source"] for e in by["causes"]}
    vg_gene = {e["source"]: e["target"] for e in by["variant_in"]}
    for e in by["driven_by"]:
        side = CLASS_DIR.get(e["target"])
        if side:
            acc.add(e["source"], side, LEVEL_W.get(e["evidence_level"], 0.3),
                    {"source": "atlas graph driven_by", "ref": e["id"], "level": e["evidence_level"]})
    gene_dis = defaultdict(list)
    for d, gn in gene_of.items():
        gene_dis[gn].append(d)
    for e in by["has_effect"]:
        side = CLASS_DIR.get(e["target"])
        gn = vg_gene.get(e["source"])
        if side and gn:
            for d in gene_dis.get(gn, []):
                acc.add(d, side, LEVEL_W.get(e["evidence_level"], 0.3),
                        {"source": "atlas graph variant_group has_effect", "ref": e["id"], "level": e["evidence_level"]})
    out = {}
    for d, r in acc.d.items():
        out[d] = {"gene": gene_of.get(d, "").replace("gene:", ""), "lof": round(r["lof"], 2), "gof": round(r["gof"], 2),
                  "direction": call(r["lof"], r["gof"]), "basis": r["basis"]}
    # variant-group level (subtype) directions, e.g. SCN2A missense-gof vs truncating
    vg = {}
    for e in by["has_effect"]:
        side = CLASS_DIR.get(e["target"])
        if side:
            vg.setdefault(e["source"], {"gene": vg_gene.get(e["source"], "").replace("gene:", ""), "sides": []})["sides"].append(
                {"side": side, "ref": e["id"], "level": e["evidence_level"]})
    return out, vg


# ---------------------------------------------------------------------------------- drugs
def drug_side(sym_of_ens):
    import pandas as pd

    moa = pd.read_parquet(RAW / "opentargets/drug_mechanism_of_action.parquet")
    mol = pd.read_parquet(RAW / "opentargets/drug_molecule.parquet")
    parent = {}
    db_of = defaultdict(set)
    name_of = {}
    for r in mol.itertuples():
        name_of[r.id] = r.name
        p = r.parentId if isinstance(r.parentId, str) else r.id
        parent[r.id] = p
        if r.childChemblIds is not None:
            for c in r.childChemblIds:
                parent.setdefault(c, r.id)
        xr = r.crossReferences
        if xr is not None:
            for x in xr:
                if x["source"].lower() == "drugbank":
                    for i in x["ids"]:
                        db_of[p].add(i)
    acts = defaultdict(list)       # parent chembl -> actions
    for r in moa.itertuples():
        at = r.actionType
        dr = "decrease" if at in DECREASE else "increase" if at in INCREASE else None
        genes = sorted({sym_of_ens[t] for t in (r.targets if r.targets is not None else []) if t in sym_of_ens})
        for c in r.chemblIds:
            p = parent.get(c, c)
            acts[p].append({"targets": genes, "action_type": at, "direction": dr, "moa": r.mechanismOfAction,
                            "target_name": r.targetName, "chembl": c})
    drugs = {}
    for p, a in acts.items():
        # dedupe
        seen, aa = set(), []
        for x in a:
            k = (tuple(x["targets"]), x["action_type"])
            if k not in seen:
                seen.add(k)
                aa.append(x)
        for db in db_of.get(p, ()):
            drugs.setdefault(db, {"name": name_of.get(p), "chembl": p, "actions": []})["actions"].extend(aa)
    return drugs, len(moa)


# Therapy summaries name the target, but the graph's target_genes field lists the DISEASE genes the therapy is
# used for. Where the drug acts on another protein (stated in the summary), the real target is set here.
TARGET_OVERRIDE = {
    "therapy:acetylcholinesterase-inhibitor-cms": (["ACHE"], "acetylcholinesterase (summary), not SYT2"),
    "therapy:binimetinib": (["MAP2K1", "MAP2K2"], "MEK1/2 (summary: MEK inhibitor)"),
    "therapy:mirdametinib": (["MAP2K1", "MAP2K2"], "MEK1/2 (summary: MEK inhibitor)"),
    "therapy:selumetinib": (["MAP2K1", "MAP2K2"], "MEK1/2 (summary: MEK1/2 inhibitor)"),
    "therapy:trametinib": (["MAP2K1", "MAP2K2"], "MEK1/2 (summary: MEK inhibitor)"),
    "therapy:rapamycin-nsml": (["MTOR"], "mTOR (summary)"),
    "therapy:tipifarnib": (["FNTA", "FNTB"], "farnesyltransferase (summary: inhibiting farnesylation)"),
    "therapy:scn8a-aso": (["SCN8A"], "lowers Scn8a (summary); used in Dravet via SCN8A, not SCN1A"),
}


# Drugs with no ChEMBL mechanism record and no direction word in their summary: direction from the literature.
# Each quote is verbatim from the PubMed abstract or title it cites.
CURATED_DIRECTION = {
    "therapy:relutrigine": ("decrease", ["SCN2A", "SCN8A"], {
        "pmid": "35037706", "doi": "10.1111/epi.17149",
        "quote": "The novel persistent sodium current inhibitor PRAX-562 has potent anticonvulsant activity"}),
    "therapy:nbi-921352": ("decrease", ["SCN8A"], {
        "pmid": "40808385", "doi": "10.4103/NRR.NRR-D-25-00260",
        "quote": "the selective Nav1.6 inhibitor NBI-921352"}),
}


def curated_therapies(graph, chembl_by_name=None):
    """Classify the atlas' own therapy nodes from modality + summary text. The basis is recorded."""
    out = {}
    tg_edges = defaultdict(set)
    for e in graph["edges"]:
        if e["type"] == "targets":
            tg_edges[e["source"]].add(e["target"])
    for n in graph["nodes"]:
        if n["type"] != "therapy":
            continue
        a = n.get("attrs", {})
        mod = a.get("modality")
        s = (n.get("summary") or "") + " " + n.get("label", "")
        sl = s.lower()
        genes = list(a.get("target_genes") or [])
        dr, basis = None, None
        if mod in ("gene_replacement",) or re.search(r"enzyme replacement|replacement of|recombinant|working \w+ gene|supply the enzyme|supply .*enzyme|gene therapy|extra copy", sl):
            dr, basis = "increase", "replacement / gene therapy (modality or summary)"
        elif mod == "chaperone" or re.search(r"chaperone|stabili[sz]e the protein", sl):
            dr, basis = "increase", "pharmacological chaperone"
        elif mod == "aso":
            if re.search(r"\blower|knockdown|reduce", sl):
                dr, basis = "decrease", "knockdown ASO (summary: lowers expression)"
            elif re.search(r"raise|full-length|splice-switching|upregulat|increase", sl):
                dr, basis = "increase", "upregulating / splice-switching ASO"
        elif re.search(r"\bblocker|inhibitor|antagonist|blocks|inhibiting|reduce sodium channel", sl):
            dr, basis = "decrease", "summary: blocker / inhibitor / antagonist"
        elif re.search(r"\bopen(er|s)?\b|activator|agonist", sl):
            dr, basis = "increase", "summary: opener / activator / agonist"
        if dr and "sodium channel" in sl:
            genes = [g for g in genes if g.startswith("SCN")]
            basis += "; targets restricted to SCN genes (sodium channel class)"
        if dr and re.search(r"potassium-channel blocker", sl):
            genes = []          # aminopyridines block Kv channels, not the disease gene; target not in atlas
            basis += "; acts on Kv channels, not on the listed disease genes -> no gene target"
        if n["id"] in TARGET_OVERRIDE:
            genes, why = TARGET_OVERRIDE[n["id"]]
            basis = (basis or "") + "; targets: " + why
        if not dr and chembl_by_name:
            for nm in [n.get("label", "")] + list(n.get("synonyms") or []):
                hit = chembl_by_name.get(nm.lower().split(" (")[0].strip())
                if hit:
                    acts = [x for x in hit["actions"] if x["direction"]]
                    if acts:
                        dr = acts[0]["direction"]
                        genes = sorted({t for x in acts if x["direction"] == dr for t in x["targets"]})
                        basis = f"ChEMBL MoA by name ({hit['name']}): " + "; ".join(sorted({x['action_type'] + ' ' + x['target_name'] for x in acts}))[:200]
                    break
        if not dr and n["id"] in CURATED_DIRECTION:
            dr, genes, ref = CURATED_DIRECTION[n["id"]]
            basis = f"literature (PMID:{ref['pmid']}): \"{ref['quote']}\""
        if re.search(r"substrate reduction|slows production", sl):
            dr, basis, genes = None, "substrate reduction: acts on an upstream enzyme, not on the disease gene", []
        out[n["id"]] = {"label": n.get("label"), "modality": mod, "direction": dr, "targets": genes,
                        "target_mechanisms": sorted(tg_edges.get(n["id"], ())), "basis": basis}
    return out


def curated_only():
    """Re-classify the atlas therapies without the raw downloads; the ChEMBL/DrugBank table is reused as is."""
    path = OUTD / "drug_direction.json"
    out = json.load(open(path))
    by_name = {}
    for v in out["drugbank"].values():
        if v.get("name"):
            by_name.setdefault(v["name"].lower(), v)
    cur = curated_therapies(json.load(open(ROOT / "data/graph.json")), by_name)
    out["curated"] = cur
    out["counts"]["curated_with_direction"] = sum(1 for v in cur.values() if v["direction"])
    out["counts"]["curated_total"] = len(cur)
    out["sources"]["curated_literature"] = "CURATED_DIRECTION in pipeline/ingest/direction_build.py (PubMed, verbatim quotes)"
    out["curated_refreshed"] = time.strftime("%Y-%m-%d")
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(json.dumps(out["counts"]))
    for k, v in cur.items():
        print(f"  {k:45s} {v['direction']!s:9s} {v['targets']} | {v['basis']}")


def main():
    if "--curated-only" in sys.argv:
        return curated_only()
    t0 = time.time()
    OUTD.mkdir(parents=True, exist_ok=True)
    sym_of_ens = {}
    with open(RAW / "hgnc_complete_set.txt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("ensembl_gene_id"):
                sym_of_ens[r["ensembl_gene_id"]] = r["symbol"]
    con = json.load(open(ROOT / "data/derived/ingest/constraint.json"))["genes"]
    acc, n_g2p, n_dm = disease_side(con)
    graph = json.load(open(ROOT / "data/graph.json"))
    gdir, vgdir = graph_side(graph)

    by_disease = defaultdict(dict)
    counts = defaultdict(int)
    for (mondo, g), r in acc.d.items():
        srcs = {b["source"] for b in r["basis"]}
        wk = r.get("weak", 0.0)
        dr = call(r["lof"] - wk, r["gof"], wk)
        conf = "weak" if srcs <= {"gnomAD v4.1"} else ("multi-source" if len(srcs - {"gnomAD v4.1"}) > 1 else "single-source")
        if srcs <= {"gnomAD v4.1"}:
            dr = None
        by_disease[mondo][g] = {"direction": dr, "lof": round(r["lof"], 2), "gof": round(r["gof"], 2),
                                "confidence": conf, "basis": r["basis"]}
        counts[str(dr)] += 1
    drugs, n_moa = drug_side(sym_of_ens)
    by_name = {}
    for v in drugs.values():
        if v.get("name"):
            by_name.setdefault(v["name"].lower(), v)
    cur = curated_therapies(graph, by_name)

    src_doc = {
        "G2P": "Gene2Phenotype mechanism classes (data/derived/global/mechanism, https://www.ebi.ac.uk/gene2phenotype)",
        "ClinGen dosage": "ClinGen dosage sensitivity HI score 3 (https://search.clinicalgenome.org)",
        "DisMech": "DisMech pathograph step labels, keyword-classified (BSD-3-Clause, commit in global/meta.json)",
        "gnomAD v4.1": "LOEUF < 0.35, weak LoF support only, never decisive",
        "atlas graph": "data/graph.json driven_by and variant_group has_effect edges (curated by this project)",
    }
    gene_out = {"generated": time.strftime("%Y-%m-%d"), "built_by": "pipeline/ingest/direction_build.py",
                "rule": "LoF = too little function, GoF = too much; direction = side with >= 2x the other's weight and >= 0.5",
                "regex": {"gof": GOF_RE.pattern, "lof": LOF_RE.pattern},
                "sources": src_doc,
                "counts": {"disease_gene_pairs": len(acc.d), "diseases": len(by_disease), "by_direction": dict(counts),
                           "g2p_class_records_used": n_g2p, "dismech_step_hits": n_dm},
                "by_disease": by_disease, "atlas_graph": gdir, "atlas_variant_groups": vgdir}
    (OUTD / "gene_direction.json").write_text(json.dumps(gene_out, separators=(",", ":")))
    dcount = defaultdict(int)
    for v in drugs.values():
        ds = {a["direction"] for a in v["actions"]}
        dcount["with_direction" if ds - {None} else "no_direction"] += 1
    drug_out = {"generated": time.strftime("%Y-%m-%d"), "built_by": "pipeline/ingest/direction_build.py",
                "sources": {"chembl_moa": "ChEMBL drug mechanisms (action_type) via Open Targets Platform drug_mechanism_of_action parquet "
                            "(https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/drug_mechanism_of_action/); "
                            "ChEMBL REST API returned HTTP 500 at build time",
                            "drugbank_ids": "Open Targets drug_molecule crossReferences (source drugbank)",
                            "curated": "data/graph.json therapy nodes, classified from modality + summary (basis per therapy)",
                            "curated_literature": "CURATED_DIRECTION in pipeline/ingest/direction_build.py (PubMed, verbatim quotes)"},
                "action_map": {"decrease": sorted(DECREASE), "increase": sorted(INCREASE)},
                "counts": {"moa_rows": n_moa, "drugbank_drugs": len(drugs), **dcount,
                           "curated_with_direction": sum(1 for v in cur.values() if v["direction"]),
                           "curated_total": len(cur)},
                "drugbank": drugs, "curated": cur}
    (OUTD / "drug_direction.json").write_text(json.dumps(drug_out, separators=(",", ":")))
    print(json.dumps(gene_out["counts"]), json.dumps(drug_out["counts"]))
    for k, v in cur.items():
        print(f"  {k:45s} {v['direction']!s:9s} {v['targets']} | {v['basis']}")
    print(f"done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
