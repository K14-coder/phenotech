"""Build biological feature profiles for the therapy-transfer scorer (stdlib only, offline after download).

Run:  python3 pipeline/eval/build_features.py            (~20 s; needs the raw downloads below)

Raw inputs (data/raw/downloads/, gitignored; re-fetch with the commands in FETCH):
  uniprot_human_reviewed_families.tsv.gz  UniProt REST stream, reviewed human: InterPro, Pfam, PANTHER,
                                          protein families, GO BP/MF/CC, subcellular location, length
  interpro_entry.list                     InterPro entry types (Family / Domain / Repeat / ...)
  hpa_tissue.tsv                          Human Protein Atlas API: RNA tissue specificity + enriched tissues
  NCBI2Reactome.txt, ReactomePathwaysRelation.txt, ReactomePathways.txt   Reactome (already present)
  go-basic.obo, hp.obo, phenotype.hpoa    ontologies + HPO annotations (already present)
Also reads data/graph.json, data/derived/global/mechanism/*.json (G2P / ClinGen classes, Reactome mid-level
pathways), data/derived/global/index.json (gene list for the breadth tables).

Writes data/derived/features/:
  atlas_features.json   per atlas disease (45): every feature profile used by the multi-feature scorer,
                        plus the global IDF tables for the tokens that occur in them
  gene_families.json    all genes in data/derived/global/index.json: PANTHER family, InterPro families /
                        domains, Pfam, protein length (compact)
  gene_tissue.json      same genes: HPA RNA tissue-specificity category + enriched tissues (nTPM)
"""
from __future__ import annotations

import gzip
import json
import math
import pathlib
import re
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "downloads"
OUT = ROOT / "data" / "derived" / "features"
FETCH = {
    "uniprot_human_reviewed_families.tsv.gz":
        "https://rest.uniprot.org/uniprotkb/stream?query=reviewed:true+AND+organism_id:9606&fields=accession,"
        "gene_primary,gene_names,length,xref_interpro,xref_pfam,xref_panther,protein_families,go_p,go_f,go_c,"
        "cc_subcellular_location&format=tsv&compressed=true",
    "interpro_entry.list": "https://ftp.ebi.ac.uk/pub/databases/interpro/current_release/entry.list",
    "hpa_tissue.tsv": "https://www.proteinatlas.org/api/search_download.php?search=&format=tsv&columns=g,eg,up,"
                      "rnats,rnatd,rnatss,rnatsm,rnabrs,rnabrsm,scl&compress=no",
}
CONSEQ_BUCKET = {  # ClinVar consequence counts on variant_group nodes -> 5-way spectrum
    "nonsense": "truncating", "frameshift": "truncating", "missense": "missense", "inframe_indel": "inframe",
    "splice": "splice", "intronic_or_splice_region": "splice", "cnv_multigene": "cnv", "cnv_single_gene": "cnv",
    "intragenic_deletion_or_duplication": "cnv",
}
SPECTRUM = ["truncating", "missense", "inframe", "splice", "cnv"]
EFFECT_CLASS = {"mech:loss-of-function": "LoF", "mech:haploinsufficiency": "HI", "mech:dominant-negative": "DN",
                "mech:gain-of-function": "GoF", "mech:lysosomal-enzyme-deficiency": "LoF",
                "mech:protein-destabilization": "destabilization"}


def djb2(s):
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def idf(df, n):
    return math.log((n + 1) / (df + 1))


# ------------------------------------------------------------------ ontologies
def parse_obo(path, rels=("part_of",)):
    parents, names, alt, obsolete = defaultdict(set), {}, {}, set()
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]":
            cur = {}
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = None
            continue
        if cur is None or not line:
            continue
        k, _, v = line.partition(": ")
        if k == "id":
            cur["id"] = v
        elif k == "name":
            names[cur["id"]] = v
        elif k == "is_a":
            parents[cur["id"]].add(v.split(" ! ")[0].strip())
        elif k == "relationship":
            r, t = v.split()[:2]
            if r in rels:
                parents[cur["id"]].add(t)
        elif k == "alt_id":
            alt[v] = cur["id"]
        elif k == "is_obsolete" and v == "true":
            obsolete.add(cur["id"])
    return parents, names, alt, obsolete


def ancestors_fn(parents):
    memo = {}

    def anc(t):
        if t in memo:
            return memo[t]
        out = {t}
        for p in parents.get(t, ()):
            out |= anc(p)
        memo[t] = out
        return out
    return anc


# ------------------------------------------------------------------ loaders
def load_uniprot():
    rows = {}
    by_gene = {}
    with gzip.open(RAW / "uniprot_human_reviewed_families.tsv.gz", "rt") as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            r = dict(zip(hdr, line.rstrip("\n").split("\t")))
            ids = lambda col: [x for x in r.get(col, "").split(";") if x]
            go = lambda col: re.findall(r"\[(GO:\d+)\]", r.get(col, ""))
            panther = ids("PANTHER")
            rec = {"acc": r["Entry"], "gene": r["Gene Names (primary)"], "length": int(r["Length"] or 0),
                   "interpro": ids("InterPro"), "pfam": ids("Pfam"),
                   "panther_family": sorted({p for p in panther if ":" not in p}),
                   "panther_subfamily": sorted({p for p in panther if ":" in p}),
                   "uniprot_family": r.get("Protein families", ""),
                   "go_bp": go("Gene Ontology (biological process)"), "go_mf": go("Gene Ontology (molecular function)"),
                   "go_cc": go("Gene Ontology (cellular component)"),
                   "subcellular": sorted(set(re.findall(r"(?:LOCATION: |\. )([A-Z][A-Za-z ,\-]+?)(?: \{|\.|;)",
                                                        r.get("Subcellular location [CC]", ""))))}
            rows[rec["acc"]] = rec
            g = rec["gene"]
            if g and (g not in by_gene):
                by_gene[g] = rec["acc"]
    return rows, by_gene


def load_interpro_types():
    t = {}
    for line in open(RAW / "interpro_entry.list", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3 and p[0].startswith("IPR"):
            t[p[0]] = (p[1], p[2])
    return t


def load_hpa():
    out = {}
    lines = open(RAW / "hpa_tissue.tsv", encoding="utf-8").read().splitlines()
    hdr = [h.strip('"') for h in lines[0].split("\t")]
    for line in lines[1:]:
        r = dict(zip(hdr, [x.strip('"') for x in line.split("\t")]))
        tis = {}
        for part in (r.get("RNA tissue specific nTPM") or "").split(";"):
            if ":" in part:
                k, v = part.rsplit(":", 1)
                try:
                    tis[k.strip()] = float(v)
                except ValueError:
                    pass
        rec = {"category": r.get("RNA tissue specificity", ""), "distribution": r.get("RNA tissue distribution", ""),
               "enriched_nTPM": tis, "subcellular_hpa": [x for x in (r.get("Subcellular location") or "").split(",") if x]}
        out.setdefault(r["Gene"], rec)
        if r.get("Uniprot"):
            for acc in r["Uniprot"].split(","):
                out.setdefault("acc:" + acc.strip(), rec)
    return out


def load_reactome():
    parents = defaultdict(set)
    for line in open(RAW / "ReactomePathwaysRelation.txt"):
        a, b = line.split()
        if a.startswith("R-HSA"):
            parents[b].add(a)
    names = {}
    for line in open(RAW / "ReactomePathways.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3 and p[2] == "Homo sapiens":
            names[p[0]] = p[1].strip()
    anc = ancestors_fn(parents)
    gene_paths = defaultdict(set)
    for line in open(RAW / "NCBI2Reactome.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 6 and p[5] == "Homo sapiens" and p[1].startswith("R-HSA"):
            gene_paths[p[0]] |= anc(p[1])
    return gene_paths, names


# ------------------------------------------------------------------ main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    g = json.loads((ROOT / "data" / "graph.json").read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    E = [e for e in g["edges"] if e["evidence_level"] != "hypothesis"]
    diseases = sorted(n for n, v in nodes.items() if v["type"] == "disease")
    gene_of = {e["target"]: e["source"] for e in E if e["type"] == "causes"}

    uni, uni_by_gene = load_uniprot()
    ipr_type = load_interpro_types()
    hpa = load_hpa()
    reac, reac_names = load_reactome()
    go_par, go_names, go_alt, _ = parse_obo(RAW / "go-basic.obo")
    go_anc = ancestors_fn(go_par)
    hp_par, hp_names, hp_alt, _ = parse_obo(RAW / "hp.obo", rels=())
    hp_anc = ancestors_fn(hp_par)
    systems = sorted(t for t, ps in hp_par.items() if "HP:0000118" in ps)

    # ---- global document frequencies (specificity): over all reviewed human proteins / Reactome genes /
    #      HPA genes / HPO-annotated diseases. A token shared by few genes is specific.
    NP = len(uni)

    def fam_tokens(rec):
        fam, dom = set(), set()
        for p in rec["panther_family"]:
            fam.add("PANTHER:" + p)
        for i in rec["interpro"]:
            typ = ipr_type.get(i, ("?",))[0]
            (fam if typ == "Family" else dom).add("InterPro:" + i)
        for p in rec["pfam"]:
            dom.add("Pfam:" + p)
        return fam, dom

    def go_tokens(ids, aspect_root=None):
        out = set()
        for t in ids:
            t = go_alt.get(t, t)
            out |= go_anc(t)
        return out
    df_fam, df_dom, df_bp, df_cc, df_mf = Counter(), Counter(), Counter(), Counter(), Counter()
    for rec in uni.values():
        f, d = fam_tokens(rec)
        df_fam.update(f)
        df_dom.update(d)
        df_bp.update(go_tokens(rec["go_bp"]))
        df_mf.update(go_tokens(rec["go_mf"]))
        df_cc.update(go_tokens(rec["go_cc"]))
    NR = len(reac)
    df_reac = Counter()
    for ps in reac.values():
        df_reac.update(ps)
    hpa_genes = [k for k in hpa if not k.startswith("acc:")]
    df_tis = Counter()
    for k in hpa_genes:
        df_tis.update(hpa[k]["enriched_nTPM"].keys())

    # HPO organ-system frequency over all annotated diseases (phenotype.hpoa, aspect P)
    dis_sys = defaultdict(set)
    for line in open(RAW / "phenotype.hpoa", encoding="utf-8"):
        if line.startswith("#") or line.startswith("database_id"):
            continue
        p = line.split("\t")
        if len(p) > 10 and p[10] == "P" and p[2] != "NOT":
            t = hp_alt.get(p[3], p[3])
            dis_sys[p[0]] |= hp_anc(t) & set(systems)
    ND = len(dis_sys)
    df_sys = Counter(s for ss in dis_sys.values() for s in ss)

    # ---- external mechanism classes (G2P / ClinGen) per atlas disease
    mdir = ROOT / "data" / "derived" / "global" / "mechanism"
    shards = {}

    def mech_records(d):
        n = nodes[d]
        gene = d.split(":")[1]
        ids = set()
        x = (n.get("xrefs") or {}).get("MONDO")
        ids |= set([x] if isinstance(x, str) else (x or []))
        for st in (n.get("attrs") or {}).get("subtypes") or []:
            if st.get("MONDO"):
                ids |= set([st["MONDO"]] if isinstance(st["MONDO"], str) else st["MONDO"])
        mechs, paths = [], set()
        for mid in sorted(ids):
            b = djb2(mid) % 64
            if b not in shards:
                shards[b] = json.loads((mdir / f"{b}.json").read_text())
            rec = shards[b]["d"].get(mid) or {}
            for m in rec.get("mechanisms", []):
                if m.get("gene") == gene:
                    mechs.append(m)
            paths |= set(rec.get("pathways") or [])
        return mechs, sorted(paths)

    by = defaultdict(list)
    for e in E:
        by[e["type"]].append(e)
    vg_of_gene = defaultdict(list)
    for e in by["variant_in"]:
        vg_of_gene[e["target"]].append(e["source"])
    eff = defaultdict(set)
    for e in by["has_effect"]:
        eff[e["source"]].add(e["target"])
    driven = defaultdict(set)
    for e in by["driven_by"]:
        driven[e["source"]].add(e["target"])
    part = defaultdict(set)
    for e in by["participates_in"]:
        part[e["source"]].add(e["target"])
    pheno = defaultdict(dict)
    for e in by["has_phenotype"]:
        p = nodes[e["target"]]
        pheno[e["source"]][p["xrefs"].get("HPO") or e["target"].split(":", 1)[1]] = float(p.get("attrs", {}).get("ic") or 0)

    atlas = {}
    used = defaultdict(set)
    for d in diseases:
        gid = gene_of[d]
        gn = nodes[gid]
        sym = gn["label"]
        acc = (gn.get("xrefs") or {}).get("UniProt") or uni_by_gene.get(sym)
        rec = uni.get(acc) or uni.get(uni_by_gene.get(sym, ""), {})
        fam, dom = fam_tokens(rec) if rec else (set(), set())
        bp = go_tokens(rec.get("go_bp", [])) if rec else set()
        mf = go_tokens(rec.get("go_mf", [])) if rec else set()
        cc = go_tokens(rec.get("go_cc", [])) if rec else set()
        entrez = str((gn.get("xrefs") or {}).get("NCBIGene") or "")
        rp = reac.get(entrez, set())
        h = hpa.get(sym) or hpa.get("acc:" + (acc or "")) or {}
        # mutation spectrum from ClinVar counts on variant_group nodes
        spec = Counter()
        for vg in vg_of_gene.get(gid, ()):
            for k, v in ((nodes[vg].get("attrs") or {}).get("clinvar_counts") or {}).items():
                spec[CONSEQ_BUCKET.get(k, "other")] += v
        tot = sum(spec[s] for s in SPECTRUM)
        spectrum = {s: round(spec[s] / tot, 4) for s in SPECTRUM} if tot else {}
        # molecular consequence classes
        mc = {}
        for m in driven[d]:
            if m in EFFECT_CLASS:
                mc[EFFECT_CLASS[m]] = max(mc.get(EFFECT_CLASS[m], 0), 1.0)
        for vg in vg_of_gene.get(gid, ()):
            for m in eff.get(vg, ()):
                if m in EFFECT_CLASS:
                    mc[EFFECT_CLASS[m]] = max(mc.get(EFFECT_CLASS[m], 0), 0.8)
        ext, mid_paths = mech_records(d)
        g2p_conseq = set()
        for m in ext:
            c = EFFECT_CLASS.get(m.get("class"))
            if c:
                mc[c] = max(mc.get(c, 0), 1.0)
            for vc in (m.get("variant_consequence") or "").split(";"):
                vc = vc.strip()
                if vc and vc != "uncertain":
                    g2p_conseq.add(vc)
        for vc in g2p_conseq:
            mc["g2p:" + vc] = 1.0
        # phenotype organ systems, IC-weighted share of the disease's phenotype annotations
        sysw = Counter()
        for hp, ic in pheno[d].items():
            for s in hp_anc(hp_alt.get(hp, hp)) & set(systems):
                sysw[s] += max(ic, 0.5)
        z = sum(sysw.values()) or 1.0
        prof = {
            "gene": sym, "uniprot": acc, "ncbigene": entrez, "protein_length": rec.get("length") if rec else None,
            "uniprot_family": rec.get("uniprot_family") if rec else "",
            "panther_subfamily": rec.get("panther_subfamily", []) if rec else [],
            "family_tokens": sorted(fam), "domain_tokens": sorted(dom),
            "go_bp": sorted(bp), "go_mf": sorted(mf), "go_cc": sorted(cc),
            "reactome": sorted(rp), "reactome_mid_level_from_mechanism_shards": mid_paths,
            "graph_processes": sorted(part.get(gid, ())),
            "hpa_category": h.get("category", ""), "hpa_distribution": h.get("distribution", ""),
            "hpa_enriched_nTPM": h.get("enriched_nTPM", {}), "hpa_subcellular": h.get("subcellular_hpa", []),
            "uniprot_subcellular": rec.get("subcellular", []) if rec else [],
            "clinvar_spectrum": spectrum, "clinvar_plp_counted": tot,
            "molecular_consequence": mc,
            "external_mechanisms": [{k: m.get(k) for k in ("class", "source", "label_verbatim", "variant_consequence",
                                                          "confidence", "url")} for m in ext],
            "phenotype_systems": {s: round(v / z, 4) for s, v in sorted(sysw.items())},
        }
        atlas[d] = prof
        used["fam"] |= fam
        used["dom"] |= dom
        used["bp"] |= bp
        used["mf"] |= mf
        used["cc"] |= cc
        used["reac"] |= rp
        used["tis"] |= set(prof["hpa_enriched_nTPM"])
        used["sys"] |= set(prof["phenotype_systems"])

    idf_tables = {
        "family": {t: round(idf(df_fam[t], NP), 4) for t in sorted(used["fam"])},
        "domain": {t: round(idf(df_dom[t], NP), 4) for t in sorted(used["dom"])},
        "go_bp": {t: round(idf(df_bp[t], NP), 4) for t in sorted(used["bp"])},
        "go_mf": {t: round(idf(df_mf[t], NP), 4) for t in sorted(used["mf"])},
        "go_cc": {t: round(idf(df_cc[t], NP), 4) for t in sorted(used["cc"])},
        "reactome": {t: round(idf(df_reac[t], NR), 4) for t in sorted(used["reac"])},
        "tissue": {t: round(idf(df_tis[t], len(hpa_genes)), 4) for t in sorted(used["tis"])},
        "phenotype_system": {t: round(idf(df_sys[t], ND), 4) for t in sorted(used["sys"])},
    }
    labels = {
        "reactome": {t: reac_names.get(t, "") for t in sorted(used["reac"])},
        "go": {t: go_names.get(t, "") for t in sorted(used["bp"] | used["mf"] | used["cc"])},
        "phenotype_system": {t: hp_names.get(t, "") for t in systems},
        "interpro": {t: ipr_type.get(t.split(":", 1)[1], ("", ""))[1] for t in sorted(used["fam"] | used["dom"])
                     if t.startswith("InterPro:")},
    }
    mechanism_go = {}
    for m, n in nodes.items():
        gid = (n.get("attrs") or {}).get("go_id") if n["type"] == "mechanism" else None
        if gid:
            gid = go_alt.get(gid, gid)
            mechanism_go[m] = {"go": gid, "idf": round(idf(max(df_bp[gid], df_mf[gid], df_cc[gid]), NP), 4),
                               "n_reviewed_proteins": max(df_bp[gid], df_mf[gid], df_cc[gid])}
    meta = {
        "generated_by": "pipeline/eval/build_features.py",
        "sources": {k: v for k, v in FETCH.items()} | {
            "reactome": "NCBI2Reactome.txt (lowest-level gene->pathway) + ReactomePathwaysRelation.txt ancestors",
            "go": "UniProt GO annotations propagated over go-basic.obo is_a + part_of",
            "hpo_systems": "direct children of HP:0000118 in hp.obo; disease frequency from phenotype.hpoa",
            "mutation_spectrum": "graph variant_group attrs.clinvar_counts (ClinVar P/LP), 5 buckets",
            "molecular_consequence": "graph driven_by (1.0) and variant_group has_effect (0.8) effect classes + "
                                     "G2P / ClinGen classes and G2P variant_consequence (data/derived/global/mechanism)"},
        "idf": "ln((N+1)/(df+1)), df counted globally: reviewed human UniProt proteins (family, domain, GO; N=%d), "
               "Reactome human genes (N=%d), HPA genes (N=%d), HPO-annotated diseases (N=%d)" % (NP, NR, len(hpa_genes), ND),
        "n_diseases": len(atlas),
        "coverage": {
            "uniprot": sum(1 for p in atlas.values() if p["family_tokens"] or p["domain_tokens"]),
            "reactome": sum(1 for p in atlas.values() if p["reactome"]),
            "hpa_enriched": sum(1 for p in atlas.values() if p["hpa_enriched_nTPM"]),
            "clinvar_spectrum": sum(1 for p in atlas.values() if p["clinvar_spectrum"]),
            "external_mechanism": sum(1 for p in atlas.values() if p["external_mechanisms"]),
        },
    }
    (OUT / "atlas_features.json").write_text(json.dumps(
        {"meta": meta, "diseases": atlas, "idf": idf_tables, "labels": labels, "mechanism_go": mechanism_go}, separators=(",", ":")))

    # ---- breadth tables for every gene in the global index (cheap: families + tissue only)
    ix = json.loads((ROOT / "data" / "derived" / "global" / "index.json").read_text())
    gi = ix["f"].index("genes")
    genes = sorted({x for r in ix["rows"] for x in (r[gi] or "").split(",") if x} |
                   {atlas[d]["gene"] for d in atlas})
    fams, tiss = {}, {}
    for s in genes:
        acc = uni_by_gene.get(s)
        if acc:
            r = uni[acc]
            f, dm = fam_tokens(r)
            fams[s] = [acc, r["length"], sorted(r["panther_family"]), sorted(t[9:] for t in f if t.startswith("InterPro:")),
                       sorted(t[9:] for t in dm if t.startswith("InterPro:")), r["pfam"]]
        h = hpa.get(s)
        if h:
            tiss[s] = [h["category"], h["enriched_nTPM"]]
    (OUT / "gene_families.json").write_text(json.dumps(
        {"f": ["uniprot", "length", "panther_family", "interpro_family", "interpro_domain_etc", "pfam"],
         "source": "UniProt REST stream (reviewed human) + InterPro entry.list types", "genes": fams},
        separators=(",", ":")))
    (OUT / "gene_tissue.json").write_text(json.dumps(
        {"f": ["hpa_rna_tissue_specificity", "enriched_tissues_nTPM"], "source": "Human Protein Atlas API",
         "genes": tiss}, separators=(",", ":")))
    print(f"atlas diseases {len(atlas)}; coverage {meta['coverage']}")
    print(f"index genes {len(genes)}: families {len(fams)}, tissue {len(tiss)}")
    for f in ("atlas_features.json", "gene_families.json", "gene_tissue.json"):
        print(f, f"{(OUT / f).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
