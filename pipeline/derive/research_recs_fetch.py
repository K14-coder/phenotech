"""Research recommendations, input step: experimental mutant structures for the 45 atlas genes.

Run:  python3 pipeline/derive/research_recs_fetch.py     (offline once the inputs below exist; ~1 min)
In:   data/raw/comparison/pdb_mutants.json
          every RCSB PDB polymer entity mapped to an atlas UniProt accession whose sequence carries an
          engineered or natural point mutation (RCSB Search API: entity_poly.rcsb_mutation_count > 0),
          with pdbx_mutation, chain ids and the UniProt alignment (RCSB Data API GraphQL). Fetched
          through a proxy fetcher because rcsb.org is blocked in the build container; see
          docs/agent-reports/research-recommendations.md for the exact queries.
      data/raw/downloads/mechsim/clinvar_subset.tsv   (ClinVar variant_summary rows for the panel genes,
          written by mechsim_fetch.py; not in git) -> P/LP germline missense protein changes per gene
      data/derived/sequences/<GENE>.json               canonical (MANE) protein, to check the reference residue
      LiteFold/PDB mirror on Hugging Face (metadata parquet + mmcif/<id[1:3]>/<id>.cif.gz); entries the mirror
          lacks were fetched once from files.rcsb.org through the proxy fetcher and cached as
          data/raw/downloads/research_recs/<id>.cif.gz (atom_site loop only)
Out:  data/raw/comparison/clinvar_missense.json   per gene: P/LP germline missense changes (1-letter, MANE numbering)
      data/raw/comparison/mutant_structures.json  per gene: PDB entities that carry a ClinVar P/LP missense
                                                  change, the representative chosen, its chain, and whether
                                                  coordinates were obtained (mirror) - plus the CA trace of the
                                                  representative (UniProt numbering) for TM-align
"""
from __future__ import annotations

import gzip
import io
import json
import re
import sys
import urllib.request
from collections import defaultdict

from dcommon import DOWNLOADS, ROOT, TODAY, read_json, write_json

IN = ROOT / "data" / "raw" / "comparison"
SEQ = ROOT / "data" / "derived" / "sequences"
CLINVAR_TSV = DOWNLOADS / "mechsim" / "clinvar_subset.tsv"
MIRROR = "https://huggingface.co/datasets/LiteFold/PDB/resolve/main"
CACHE = DOWNLOADS / "research_recs"
AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H",
       "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
       "Tyr": "Y", "Val": "V"}
THREE = {k.upper(): v for k, v in AA3.items()}
P_MISSENSE = re.compile(r"\(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)")
TOKEN = re.compile(r"\b([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])\b")


def atlas_genes():
    ms = read_json(ROOT / "data" / "derived" / "mechsim.json")
    return {p["gene"]: p["structure"].get("uniprot") for p in ms["profiles"] if p["kind"] == "atlas"}


def clinvar_missense(genes):
    """P/LP (ClinSigSimple 1) germline single-gene missense records, as 1-letter changes."""
    out = defaultdict(dict)
    with open(CLINVAR_TSV, encoding="utf-8") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        ix = {h: i for i, h in enumerate(header)}
        for line in fh:
            f = line.rstrip("\n").split("\t")
            g = f[ix["GeneSymbol"]]
            if g not in genes or f[ix["ClinSigSimple"]] != "1" or "germline" not in f[ix["OriginSimple"]]:
                continue
            m = P_MISSENSE.search(f[ix["Name"]])
            if not m or m.group(3) == "Ter" or m.group(1) not in AA3 or m.group(3) not in AA3:
                continue
            ch = f"{AA3[m.group(1)]}{m.group(2)}{AA3[m.group(3)]}"
            out[g].setdefault(ch, f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{f[ix['VariationID']]}/")
    return {g: dict(sorted(v.items(), key=lambda kv: int(kv[0][1:-1]))) for g, v in sorted(out.items())}


def mirror_index():
    import pandas as pd
    CACHE.mkdir(parents=True, exist_ok=True)
    ids = set()
    for split in ("train", "test"):
        path = CACHE / f"litefold_{split}.parquet"
        if not path.exists():
            urllib.request.urlretrieve(f"{MIRROR}/data/{split}-00000-of-00001.parquet", path)
        ids |= set(pd.read_parquet(path, columns=["pdb_id"])["pdb_id"].str.upper())
    return ids


def fetch_cif(entry):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{entry.lower()}.cif.gz"
    if not path.exists():
        e = entry.lower()
        urllib.request.urlretrieve(f"{MIRROR}/mmcif/{e[1:3]}/{e}.cif.gz", path)
    return path


def ca_trace(entry, entity_id, chains, align):
    """CA atoms of the first listed chain of this entity, renumbered to UniProt via the RCSB alignment.
    Returns {uniprot_pos: (aa, x, y, z)}."""
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    with gzip.open(fetch_cif(entry), "rt") as fh:
        d = MMCIF2Dict(io.StringIO(fh.read()))
    cols = ["_atom_site.label_atom_id", "_atom_site.label_entity_id", "_atom_site.auth_asym_id",
            "_atom_site.label_seq_id", "_atom_site.label_comp_id", "_atom_site.Cartn_x", "_atom_site.Cartn_y",
            "_atom_site.Cartn_z", "_atom_site.pdbx_PDB_model_num", "_atom_site.label_alt_id"]
    rows = zip(*(d[c] for c in cols))
    seq2ref = {}
    for reg in align:
        for k in range(reg["length"]):
            seq2ref[reg["entity_beg_seq_id"] + k] = reg["ref_beg_seq_id"] + k
    out, chain, model = {}, None, None
    for atom, ent, asym, seq, comp, x, y, z, mod, alt in rows:
        if atom != "CA" or ent != str(entity_id) or seq in (".", "?"):
            continue
        if model is None:
            model = mod
        if mod != model or alt not in (".", "?", "A"):
            continue
        if chain is None:
            chain = asym if asym in chains else None
            if chain is None:
                chain = asym
        if asym != chain:
            continue
        ref = seq2ref.get(int(seq))
        if ref is not None and comp in THREE:
            out[ref] = (THREE[comp], float(x), float(y), float(z))
    return chain, out


def main():
    genes = atlas_genes()
    acc2gene = {a: g for g, a in genes.items()}
    clin = clinvar_missense(set(genes))
    write_json(IN / "clinvar_missense.json", {
        "source": "ClinVar variant_summary.txt (ClinSigSimple = 1, germline, single-gene records), protein change "
                  "from the record name (MANE / RefSeq numbering)",
        "retrieved": TODAY, "genes": clin}, compact=True)
    seqs = {g: read_json(SEQ / f"{g}.json").get("protein", "") for g in genes if (SEQ / f"{g}.json").exists()}
    pdb = read_json(IN / "pdb_mutants.json")
    mirrored = mirror_index()
    per_gene = defaultdict(list)
    for e in pdb["entities"]:
        accs = (e.get("rcsb_polymer_entity_container_identifiers") or {}).get("uniprot_ids") or []
        gene = next((acc2gene[a] for a in accs if a in acc2gene), None)
        text = (e.get("rcsb_polymer_entity") or {}).get("pdbx_mutation") or ""
        if not gene or not text:
            continue
        toks = ["".join(t) for t in TOKEN.findall(text.upper())]
        seq = seqs.get(gene, "")
        align = next((a["aligned_regions"] for a in e.get("rcsb_polymer_entity_align") or []
                      if a.get("reference_database_accession") == genes[gene]), [])
        # author numbering is usually UniProt numbering; some entries number the mature chain (e.g. GBA1
        # N370S = p.Asn409Ser), so the alignment offset is tried second
        offsets = [0] + sorted({r["ref_beg_seq_id"] - r["entity_beg_seq_id"] for r in align} - {0})
        disease, author = [], {}
        for off in offsets:
            hits = []
            for t in toks:
                pos = int(t[1:-1]) + off
                if 0 < pos <= len(seq) and seq[pos - 1] == t[0] and f"{t[0]}{pos}{t[-1]}" in clin.get(gene, {}):
                    hits.append((t, f"{t[0]}{pos}{t[-1]}"))
            if hits:
                disease = [h[1] for h in hits]
                author = {h[1]: h[0] for h in hits if h[0] != h[1]}
                break
        if not disease:
            continue
        toks_ref = set(author.values()) | set(disease)
        covered = sum(r["length"] for r in align)
        per_gene[gene].append({
            "entity": e["rcsb_id"], "entry": e["rcsb_id"].split("_")[0], "pdbx_mutation": text,
            "disease_mutations": disease, "other_mutations": [t for t in toks if t not in toks_ref],
            "author_numbering": author,
            "chains": (e.get("rcsb_polymer_entity_container_identifiers") or {}).get("auth_asym_ids") or [],
            "uniprot_residues_covered": covered, "align": align,
            "clinvar": {t: clin[gene][t] for t in disease},
            "mirrored": e["rcsb_id"].split("_")[0] in mirrored,
            "coordinates": ("LiteFold/PDB mirror" if e["rcsb_id"].split("_")[0] in mirrored else
                            "files.rcsb.org via proxy fetcher (cached)"
                            if (CACHE / f"{e['rcsb_id'].split('_')[0].lower()}.cif.gz").exists() else None),
        })
    out = {}
    for gene in sorted(genes):
        cands = per_gene.get(gene, [])
        # representative: coordinates available, fewest extra (engineered) mutations, widest coverage
        ranked = sorted(cands, key=lambda c: (c["coordinates"] is None, len(c["other_mutations"]),
                                              -c["uniprot_residues_covered"], c["entity"]))
        rep = None
        for c in ranked:
            if c["coordinates"] is None:
                break
            try:
                chain, trace = ca_trace(c["entry"], int(c["entity"].split("_")[1]), c["chains"], c["align"])
            except Exception as exc:  # noqa: BLE001 - a missing/odd file just means "no coordinates"
                print(f"  {c['entity']}: {exc}", file=sys.stderr)
                continue
            muts_seen = [t for t in c["disease_mutations"] if trace.get(int(t[1:-1]), ("",))[0] == t[-1]]
            if len(trace) < 30 or not muts_seen:
                continue
            rep = {k: c[k] for k in ("entity", "entry", "pdbx_mutation", "disease_mutations", "other_mutations",
                                     "author_numbering", "clinvar", "uniprot_residues_covered",
                                     "coordinates")}
            rep.update({"chain": chain, "mutations_verified_in_coordinates": muts_seen,
                        "n_ca": len(trace), "residue_range": [min(trace), max(trace)],
                        "ca": [[p, *trace[p]] for p in sorted(trace)]})
            break
        out[gene] = {
            "uniprot": genes[gene],
            "n_clinvar_missense": len(clin.get(gene, {})),
            "n_mutant_entities": len(cands),
            "mutant_entities": [{k: c[k] for k in ("entity", "pdbx_mutation", "disease_mutations", "coordinates")}
                                for c in sorted(cands, key=lambda c: c["entity"])],
            "representative": rep,
        }
        if cands:
            print(f"{gene}: {len(cands)} disease-mutant entities; rep "
                  f"{rep['entity'] + ' ' + ','.join(rep['disease_mutations']) if rep else 'none with coordinates'}")
    write_json(IN / "mutant_structures.json", {
        "source": "RCSB PDB (pdb_mutants.json) x ClinVar P/LP missense; coordinates from the LiteFold/PDB "
                  "Hugging Face mirror of the wwPDB mmCIF archive",
        "retrieved": TODAY,
        "rule": "an entity counts when its pdbx_mutation lists a substitution that is a ClinVar P/LP germline "
                "missense change of the same gene AND the reference residue matches the MANE protein",
        "genes": out}, compact=True)


if __name__ == "__main__":
    main()
