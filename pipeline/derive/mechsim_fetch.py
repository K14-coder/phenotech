"""Mechanistic similarity, step 1 of 2: download the sources and write small, committed extracts.

Run:  python3 pipeline/derive/mechsim_fetch.py [--refresh]      (needs pandas + pyarrow; ~2 min)
      python3 pipeline/derive/mechsim_fetch.py --pharmacology    (ChEMBL 36, ~1 GB download, after the above)
      python3 pipeline/derive/mechsim_structure.py               (RCSB PDB inventory + AlphaFold TM-align)
Then: python3 pipeline/derive/mechsim.py                        (offline, reads only the extracts)

Which diseases
  * the 45 atlas umbrella diseases (one per gene, from data/graph.json `causes` edges);
  * a channelopathy panel: every gene that UniProt/HPA marks as an ion channel ("Ion channel"
    molecular-function keyword or an "... ion channels" protein class) AND that causes at least one
    Mendelian disease in the global index (gsrc = 1). One entity per gene, "<GENE>-related
    channelopathies", grouping all of that gene's MONDO entries.

Sources (bulk files only; the policy-restricted REST APIs are not needed)
  HPO        hp.obo + phenotype.hpoa             github.com/obophenotype/human-phenotype-ontology releases
  ClinVar    variant_summary.txt                 NCBI ClinVar, via the huggingworld/clinvar_variant_summary mirror
                                                 (streamed, only rows for entity genes are kept)
  Pathways   MSigDB canonical pathways           Reactome, WikiPathways, KEGG, BioCarta, PID gene sets
                                                 (ToppGene export, pankajrajdeo/Pathway_ToppGene)
  STRING     v12 network among the atlas genes   data/raw/comparison/string_network.tsv (fetched once, kept)
  GTEx       v10 gene median TPM                 storage.googleapis.com/adult-gtex
  HPA        proteinatlas.json                   Human Protein Atlas (LiteFold/HumanProteinAtlas mirror):
                                                 protein class, molecular-function keywords, UniProt accession
  Pfam       Swiss-Prot sequences + Pfam labels  ProtInfer Swiss-Prot/Pfam export (DanielHesslow/SwissProt-Pfam)
             Pfam-A.clans.tsv                    family names and clans (structural superfamilies), LiteFold/Pfam mirror

Writes data/raw/comparison/:
  entities.json   entity list (gene, kind, label, MONDO / OMIM / ORPHA ids, gene sets)
  hpo.json        per entity: HPO terms with IC, mapped to tissue/organ anchors
  clinvar.json    per gene: P/LP germline counts by variant type and by molecular consequence
  pathways.json   per gene: canonical pathway memberships, with set sizes and URLs
  gtex.json       per gene: median TPM per GTEx tissue
  proteins.json   per gene: UniProt accession, sequence, Pfam ids, HPA protein class / function keywords
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict

import pandas as pd

from dcommon import DOWNLOADS, ROOT, TODAY, read_json, write_json

sys.path.append(str(ROOT / "pipeline" / "biology"))
import hpo  # noqa: E402

DL = DOWNLOADS / "mechsim"
OUT = ROOT / "data" / "raw" / "comparison"
REFRESH = "--refresh" in sys.argv
HF = "https://huggingface.co/datasets"
HPO_REL = "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download"
SOURCES = {
    DOWNLOADS / "hp.obo": f"{HPO_REL}/hp.obo",
    DOWNLOADS / "phenotype.hpoa": f"{HPO_REL}/phenotype.hpoa",
    DL / "gtex_median_tpm.gct.gz": "https://storage.googleapis.com/adult-gtex/bulk-gex/v10/rna-seq/"
                                   "GTEx_Analysis_v10_RNASeQCv2.4.2_gene_median_tpm.gct.gz",
    DL / "hpa.jsonl": f"{HF}/LiteFold/HumanProteinAtlas/resolve/main/tables/"
                      "annotation_human_protein_atlas_proteinatlas.json.gz.jsonl",
    DL / "toppgene_pathway.parquet": f"{HF}/pankajrajdeo/Pathway_ToppGene/resolve/main/Pathway(ToppGene).parquet",
    **{DL / f"sp_pfam_{s}.parquet": f"{HF}/DanielHesslow/SwissProt-Pfam/resolve/main/data/{s}.parquet"
       for s in ("train-00000-of-00001", "dev-00000-of-00001", "test-00000-of-00001")},
    DL / "pfam_clans.jsonl": f"{HF}/LiteFold/Pfam/resolve/main/tables/"
                             "annotation_pfam_current_release_Pfam-A.clans.tsv.gz.jsonl",
}
CLINVAR_URL = f"{HF}/huggingworld/clinvar_variant_summary/resolve/main/variant_summary.tsv"

# Tissue / organ anchors over HPO: a disease's symptom profile is scored against each anchor's
# descendants. Ids are checked against hp.obo on every run.
TISSUE_ANCHORS = {
    "brain (central nervous system)": ["HP:0002011", "HP:0001250", "HP:0012759", "HP:0011446", "HP:0001298",
                                       "HP:0100022"],
    "peripheral nerve": ["HP:0000759", "HP:0009830"],
    "neuromuscular junction": ["HP:0003473"],
    "skeletal muscle": ["HP:0003011", "HP:0003457"],
    "heart": ["HP:0001627", "HP:0011675", "HP:0001638"],
    "eye / retina": ["HP:0000478"],
    "ear / hearing": ["HP:0000598"],
    "skin": ["HP:0001574"],
    "skeleton": ["HP:0000924"],
    "digestive system / liver": ["HP:0025031"],
    "kidney": ["HP:0000077"],
    "respiratory system": ["HP:0002086"],
    "blood": ["HP:0001871"],
    "immune system": ["HP:0002715"],
    "endocrine system": ["HP:0000818"],
    "metabolism / homeostasis": ["HP:0001939"],
    "head and face": ["HP:0000152"],
    "growth": ["HP:0001507"],
    "neoplasm": ["HP:0002664"],
    "genitourinary system": ["HP:0000119"],
}
# Gene sets named after a disease, syndrome or mutant are disease-gene lists, not pathways:
# they would make "same pathway" circular, so they are dropped.
NOT_A_PATHWAY = re.compile(
    r"SYNDROME|DISEASE|DISORDER|EPILEP|DEFICIENC|CANCER|CARCINOMA|LEUKEMIA|LYMPHOMA|MELANOMA|GLIOMA|"
    r"TUMOR|COPY_NUMBER|DELETION|DUPLICATION|MUTANT|MUTATION|_MODEL|ONCOGENIC|INFECTION|DIABET|"
    r"CARDIOMYOPATHY|ALZHEIMER|PARKINSON|HUNTINGTON|SCLEROSIS|DYSTROPHY|ATAXIA|DRAVET|RETT|AUTISM|"
    r"ADDICTION|MICRODELETION|ANEMIA|HEPATITIS|COVID|SARS|HIV|INFLUENZA|MEASLES|TUBERCULOSIS|"
    r"_GENES$|^WP_.*GENES|PATHOGENIC|LONG_QT|ARRHYTHMOGENIC|NEURODEGENERATION")
MAX_PATHWAY_GENES = 500
MAX_GROUP_GENES = 5   # a multi-gene MONDO entry with more genes than this is a clinical group, not shared biology


def download(path, url):
    if path.exists() and path.stat().st_size and not REFRESH:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {path.name}")
    subprocess.run(["curl", "-sSL", "--fail", "--max-time", "1800", "-o", str(path), url], check=True)


def stream_clinvar(genes, dest):
    if dest.exists() and dest.stat().st_size and not REFRESH:
        have = set(json.loads((dest.with_suffix(".genes.json")).read_text()))
        if genes <= have:
            return
    print(f"  streaming ClinVar variant_summary (~4 GB) for {len(genes)} genes")
    proc = subprocess.Popen(["curl", "-sSL", "--fail", CLINVAR_URL], stdout=subprocess.PIPE, text=True)
    n = 0
    with dest.open("w") as out:
        for i, line in enumerate(proc.stdout):
            if i == 0:
                out.write(line)
                continue
            syms = line.split("\t", 6)[4]
            if set(syms.split(";")) & genes:
                out.write(line)
                n += 1
    if proc.wait() != 0:
        sys.exit("ClinVar download failed")
    dest.with_suffix(".genes.json").write_text(json.dumps(sorted(genes)))
    print(f"  kept {n} ClinVar rows")


# ---------------------------------------------------------------- ClinVar classification
VARIANT_TYPES = {
    "single nucleotide variant": "single nucleotide substitution",
    "Deletion": "deletion",
    "Duplication": "duplication",
    "Insertion": "insertion",
    "Indel": "insertion-deletion (indel)",
    "Inversion": "inversion",
    "Microsatellite": "repeat expansion / contraction",
    "copy number loss": "copy-number loss",
    "copy number gain": "copy-number gain",
    "Translocation": "translocation",
    "Complex": "complex rearrangement",
}
P_DOT = re.compile(r"\(p\.([^)]*)\)")


def consequence(name: str, vtype: str) -> str:
    """Molecular consequence of one ClinVar record from its HGVS name."""
    p = P_DOT.search(name)
    prot = p.group(1) if p else ""
    if vtype in ("copy number loss", "copy number gain"):
        return "whole-gene or multi-exon copy-number change"
    if prot:
        if "fs" in prot:
            return "frameshift"
        if re.search(r"(Ter|\*)$", prot) and not re.search(r"Ter\d+\w*ext", prot):
            return "nonsense (stop gained)"
        if re.match(r"Met1(\?|[A-Z][a-z]{2}|del)", prot) or prot == "M1?":
            return "start lost"
        if "ext" in prot:
            return "stop lost"
        if prot.endswith("="):
            return "synonymous"
        if re.search(r"(del|ins|dup)", prot):
            return "in-frame insertion/deletion"
        if re.match(r"[A-Z][a-z]{2}\d+[A-Z][a-z]{2}$", prot):
            return "missense"
        return "other protein change"
    c = re.search(r":c\.(\S+)", name)
    cdot = c.group(1) if c else ""
    if re.search(r"\d[+-][12](?!\d)", cdot):
        return "canonical splice site"
    if re.search(r"\d[+-]\d+", cdot):
        return "intronic / splice region"
    if vtype in ("Deletion", "Duplication") and not cdot:
        return "whole-gene or multi-exon copy-number change"
    if cdot.startswith("-") or cdot.startswith("*"):
        return "untranslated region"
    return "other / non-coding"


def clinvar_counts(path, genes):
    df = pd.read_csv(path, sep="\t", low_memory=False, dtype=str)
    df = df[(df["ClinSigSimple"] == "1") & df["OriginSimple"].str.contains("germline", na=False)]
    df = df[df["Assembly"].isin(["GRCh38", "na"])].drop_duplicates("VariationID")
    out = {}
    for g in sorted(genes):
        single = df[df["GeneSymbol"] == g]
        multi = df[df["GeneSymbol"].str.contains(rf"(?:^|;){g}(?:;|$)", regex=True) & (df["GeneSymbol"] != g)]
        vt, cq = Counter(), Counter()
        for name, vtype in zip(single["Name"].fillna(""), single["Type"].fillna("")):
            vt[VARIANT_TYPES.get(vtype, "other")] += 1
            cq[consequence(name, vtype)] += 1
        out[g] = {"n": int(len(single)), "variant_type": dict(vt.most_common()),
                  "consequence": dict(cq.most_common()), "multi_gene_records": int(len(multi))}
    return out


# ---------------------------------------------------------------- entities
def load_index():
    idx = read_json(ROOT / "data" / "derived" / "global" / "index.json")
    return [dict(zip(idx["f"], r)) for r in idx["rows"]]


def hpa_rows(path):
    with path.open() as fh:
        for line in fh:
            yield json.loads(line)["row"]


def is_channel(r):
    cls = r.get("Protein class") or []
    mf = r.get("Molecular function") or []
    return "Ion channel" in mf or any("ion channel" in c.lower() for c in cls)


def pfam_clans(path):
    """Pfam-A.clans.tsv as JSON lines; the mirror turned the TSV header into keys, so the first data
    row (PF00001) is the key set itself."""
    out = {}
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)["row"]
            keys = list(row)
            if not out:
                out[keys[4]] = {"clan": keys[2], "clan_name": keys[3], "name": keys[1], "description": keys[0]}
            v = list(row.values())
            out[v[4]] = {"clan": v[2] or None, "clan_name": v[3] or None, "name": v[1], "description": v[0]}
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("== downloads")
    for path, url in SOURCES.items():
        download(path, url)

    graph = read_json(ROOT / "data" / "graph.json")
    nodes = {n["id"]: n for n in graph["nodes"]}
    atlas = {}
    for e in graph["edges"]:
        if e["type"] == "causes" and e["target"] in nodes:
            atlas[nodes[e["source"]]["label"]] = nodes[e["target"]]
    rows = load_index()
    by_mondo = {r["id"]: r for r in rows}
    by_gene = defaultdict(list)
    for r in rows:
        gs = [g for g in r["genes"].split(",") if g]
        if r["gsrc"] == 1 and 0 < len(gs) <= MAX_GROUP_GENES:
            for g in gs:
                by_gene[g].append(r)

    print("== Human Protein Atlas")
    hpa = {}
    channel_genes = set()
    for r in hpa_rows(DL / "hpa.jsonl"):
        g = r.get("Gene")
        if not g:
            continue
        if is_channel(r) and any(len([x for x in m["genes"].split(",") if x]) == 1 for m in by_gene.get(g, [])):
            channel_genes.add(g)
        if g in atlas or is_channel(r):
            hpa[g] = r
    genes = set(atlas) | channel_genes
    print(f"  {len(atlas)} atlas genes + {len(channel_genes - set(atlas))} more ion-channel genes = {len(genes)}")

    entities = []
    for g in sorted(genes):
        if g in atlas:
            d = atlas[g]
            mondo = [m for m in (d.get("xrefs", {}).get("MONDO") or []) if m in by_mondo]
            members = [by_mondo[m] for m in mondo]
            members += [m for m in by_gene[g] if m["id"] not in mondo]
            ent = {"id": d["id"], "gene": g, "kind": "atlas", "label": d["label"],
                   "family": (d.get("attrs") or {}).get("family") or "snareopathy"}
        else:
            members = by_gene[g]
            ent = {"id": f"panel:{g}", "gene": g, "kind": "channel_panel", "label": f"{g}-related channelopathies",
                   "family": None}
        member_genes = set()
        for m in members:
            gs = {x for x in m["genes"].split(",") if x}
            if len(gs) <= MAX_GROUP_GENES:
                member_genes |= gs
        ent["channel"] = g in channel_genes or is_channel(hpa.get(g, {}))
        ent["mondo"] = sorted({m["id"] for m in members})
        ent["diseases"] = sorted({m["name"] for m in members})[:12]
        ent["omim"] = sorted({f"OMIM:{x}" for m in members for x in m["omim"].split(",") if x})
        ent["orpha"] = sorted({f"ORPHA:{x}" for m in members for x in m["orpha"].split(",") if x})
        ent["genes"] = sorted(member_genes | {g})
        entities.append(ent)
    write_json(OUT / "entities.json", {"generated": TODAY, "entities": entities})

    print("== HPO")
    terms, alt_map, obo_version = hpo.parse_obo()
    anc = hpo.ancestors_fn(terms)
    rows_hpoa, hpoa_version = hpo.parse_hpoa(alt_map, terms)
    for anchors in TISSUE_ANCHORS.values():
        for a in anchors:
            if a not in terms or terms[a]["obsolete"]:
                sys.exit(f"tissue anchor {a} is missing or obsolete in hp.obo {obo_version}")
    direct = defaultdict(set)
    for r in rows_hpoa:
        if r["aspect"] == "P" and r["qualifier"] != "NOT":
            direct[r["database_id"]].add(r["hpo_id"])
    counts = Counter()
    for ts in direct.values():
        for t in frozenset().union(*(anc(t) for t in ts)):
            counts[t] += 1
    import math
    n_dis = len(direct)
    ic = {t: round(-math.log(c / n_dis), 3) for t, c in counts.items()}
    graph_pheno = defaultdict(set)
    for e in graph["edges"]:
        if e["type"] == "has_phenotype":
            graph_pheno[e["source"]].add(e["target"].removeprefix("phenotype:"))
    per_entity, used = {}, set()
    for ent in entities:
        ts = set()
        for did in ent["omim"] + ent["orpha"]:
            ts |= direct.get(did, set())
        ts |= {alt_map.get(t, t) for t in graph_pheno.get(ent["id"], set())}
        ts = {t for t in ts if t in terms and not terms[t]["obsolete"]}
        per_entity[ent["id"]] = sorted(ts)
        used |= ts
    term_info = {}
    for t in used:
        a = anc(t)
        term_info[t] = {"name": terms[t].get("name"), "ic": ic.get(t, round(math.log(n_dis), 3)),
                        "tissues": [k for k, anchors in TISSUE_ANCHORS.items() if any(x in a for x in anchors)]}
    write_json(OUT / "hpo.json", {"hp_obo": obo_version, "phenotype_hpoa": hpoa_version, "n_diseases_for_ic": n_dis,
                                  "tissue_anchors": TISSUE_ANCHORS, "terms": term_info, "entities": per_entity},
               compact=True)

    print("== ClinVar")
    cv_path = DL / "clinvar_subset.tsv"
    stream_clinvar(genes, cv_path)
    write_json(OUT / "clinvar.json", {"source": "ClinVar variant_summary.txt (mirror: huggingworld/clinvar_variant_summary)",
                                      "filter": "ClinSigSimple = 1 (pathogenic or likely pathogenic, current), germline origin, "
                                                "GRCh38 or assembly-free records, one row per VariationID, single-gene records only",
                                      "retrieved": TODAY, "genes": clinvar_counts(cv_path, genes)})

    print("== pathways")
    pw = pd.read_parquet(DL / "toppgene_pathway.parquet").drop_duplicates(["concept_id", "symbol"])
    pw = pw[~pw["concept_name"].str.contains(NOT_A_PATHWAY)]
    sizes = pw.groupby("concept_id")["symbol"].nunique()
    pw = pw[pw["concept_id"].map(sizes) <= MAX_PATHWAY_GENES]
    sub = pw[pw["symbol"].isin(genes)]
    sets = {}
    for cid, grp in sub.groupby("concept_id"):
        first = grp.iloc[0]
        sets[cid] = {"name": first["concept_name"], "origin": first["concept_origin"], "url": first["url"],
                     "size": int(sizes[cid])}
    write_json(OUT / "pathways.json", {
        "source": "MSigDB canonical pathways (Reactome, WikiPathways, KEGG, BioCarta, PID) via the ToppGene export",
        "n_sets_universe": int(pw["concept_id"].nunique()),
        "n_genes_universe": int(pw["symbol"].nunique()),
        "dropped": f"sets named after a disease/syndrome/mutant (regex in mechsim_fetch.py) and sets > {MAX_PATHWAY_GENES} genes",
        "sets": sets,
        "genes": {g: sorted(grp["concept_id"].unique().tolist()) for g, grp in sub.groupby("symbol")}}, compact=True)

    print("== GTEx")
    with gzip.open(DL / "gtex_median_tpm.gct.gz", "rt") as fh:
        gt = pd.read_csv(fh, sep="\t", skiprows=2)
    gt = gt[gt["Description"].isin(genes)].drop_duplicates("Description")
    tissues = [c for c in gt.columns if c not in ("Name", "Description")]
    write_json(OUT / "gtex.json", {"source": "GTEx v10 gene median TPM", "tissues": tissues,
                                   "genes": {r["Description"]: [round(float(r[t]), 2) for t in tissues]
                                             for _, r in gt.iterrows()}}, compact=True)

    print("== proteins (UniProt accession from HPA; sequence + Pfam from Swiss-Prot)")
    acc = {}
    for g in genes:
        u = (hpa.get(g) or {}).get("Uniprot") or []
        if u:
            acc[g] = u[0]
    frames = [pd.read_parquet(p) for p in sorted(DL.glob("sp_pfam_*.parquet"))]
    sp = pd.concat(frames)
    sp = sp[sp["id"].isin(set(acc.values()))].drop_duplicates("id").set_index("id")
    proteins = {}
    for g in sorted(genes):
        a = acc.get(g)
        r = hpa.get(g) or {}
        rec = {"uniprot": a, "protein_class": r.get("Protein class") or [],
               "molecular_function": r.get("Molecular function") or [],
               "biological_process": r.get("Biological process") or [],
               "tissue_specificity": r.get("RNA tissue specificity"),
               "tissue_specific_ntpm": r.get("RNA tissue specific nTPM") or {},
               "subcellular": r.get("Subcellular main location") or []}
        if a in sp.index:
            row = sp.loc[a]
            rec["sequence"] = row["seq"]
            rec["pfam"] = sorted(x.replace("Pfam:", "") for x in json.loads(row["labels_str"].replace("'", '"')))
        proteins[g] = rec
    clans = pfam_clans(DL / "pfam_clans.jsonl")
    used = sorted({p for r in proteins.values() for p in r.get("pfam", [])})
    pfam_info = {p: clans.get(p, {"name": None}) for p in used}
    missing = [g for g, r in proteins.items() if "sequence" not in r]
    print(f"  {len(proteins) - len(missing)} sequences; missing: {missing}")
    write_json(OUT / "proteins.json", {"source": "Human Protein Atlas (class, keywords, UniProt id); Swiss-Prot "
                                                 "sequence and Pfam labels via the ProtInfer export",
                                       "pfam": pfam_info, "genes": proteins}, compact=True)


if __name__ == "__main__" and "--pharmacology" not in sys.argv:
    main()


# ---------------------------------------------------------------- pharmacology (ChEMBL 36)
CHEMBL = f"{HF}/lukaskim/ChEMBL-36/resolve/main"
PCHEMBL_MIN = 5.0  # <= 10 uM (many approved channel blockers act in the low-micromolar range)


def pharmacology():
    """Compounds with measured potency (pChEMBL >= 6) on each protein, from ChEMBL 36 bioactivities.
    Targets: ChEMBL SINGLE PROTEIN targets, plus PROTEIN COMPLEX targets that contain the protein
    (most channel pharmacology is measured on assembled heteromers); the complex attribution is flagged."""
    d = DL / "chembl"
    files = {"targets.parquet": "targets/train-00000-of-00001.parquet",
             **{f"pairs_{i}.parquet": f"molecule_target_pairs/train-0000{i}-of-00007.parquet" for i in range(7)},
             **{f"mol_{i}.parquet": f"molecules/train-0000{i}-of-00003.parquet" for i in range(3)}}
    for name, rel in files.items():
        download(d / name, f"{CHEMBL}/{rel}")
    prot = read_json(OUT / "proteins.json")["genes"]
    acc = {v["uniprot"]: g for g, v in prot.items() if v.get("uniprot")}
    t = pd.read_parquet(d / "targets.parquet")
    t = t[t["accession"].isin(acc) & t["target_type"].isin(["SINGLE PROTEIN", "PROTEIN COMPLEX"])]
    tgt = defaultdict(set)
    for tid, a, ttype in zip(t["target_chembl_id"], t["accession"], t["target_type"]):
        tgt[tid].add((acc[a], ttype))
    cols = ["chembl_id", "target_chembl_id", "pchembl_value"]
    pairs = pd.concat([pd.read_parquet(d / f"pairs_{i}.parquet", columns=cols) for i in range(7)])
    pairs = pairs[pairs["target_chembl_id"].isin(tgt) & (pairs["pchembl_value"] >= PCHEMBL_MIN)]
    mols = pd.concat([pd.read_parquet(d / f"mol_{i}.parquet", columns=["chembl_id", "max_phase", "first_approval"])
                      for i in range(3)])
    mols = mols[mols["chembl_id"].isin(set(pairs["chembl_id"]))].set_index("chembl_id")
    out = defaultdict(lambda: {"single": {}, "complex": {}})
    for cid, tid, pv in zip(pairs["chembl_id"], pairs["target_chembl_id"], pairs["pchembl_value"]):
        for g, ttype in tgt[tid]:
            bucket = out[g]["single" if ttype == "SINGLE PROTEIN" else "complex"]
            bucket[cid] = max(bucket.get(cid, 0), round(float(pv), 2))
    phase = {c: (None if pd.isna(p) else int(p)) for c, p in mols["max_phase"].items()}
    genes = {}
    for g, v in out.items():
        compounds = {**v["complex"], **v["single"]}
        genes[g] = {"targets": sorted(tid for tid, s in tgt.items() if any(x[0] == g for x in s)),
                    "n_active": len(compounds), "n_active_single_protein": len(v["single"]),
                    "approved": sorted(c for c in compounds if phase.get(c) == 4),
                    "clinical": sorted(c for c in compounds if phase.get(c) in (1, 2, 3)),
                    "active": sorted(compounds, key=lambda c: -compounds[c])}
    write_json(OUT / "pharmacology.json", {
        "source": "ChEMBL 36 bioactivities (lukaskim/ChEMBL-36 mirror), CC BY-SA 4.0",
        "filter": f"pChEMBL >= {PCHEMBL_MIN} (<= 1 uM), '=' relation, nM units; SINGLE PROTEIN and PROTEIN COMPLEX targets",
        "retrieved": TODAY, "genes": genes}, compact=True)
    print(f"  pharmacology for {len(genes)} genes, {sum(g['n_active'] for g in genes.values())} gene-compound links")


if __name__ == "__main__" and "--pharmacology" in sys.argv:
    pharmacology()
