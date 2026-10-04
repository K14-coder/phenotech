"""Mechanistic similarity, structure step: PDB inventory (RCSB) + AlphaFold all-vs-all TM-align.

Run:  python3 pipeline/derive/mechsim_structure.py [--workers 4]   (needs numpy + tmtools; hours on 4 cores,
      resumable: finished pairs are cached in data/raw/downloads/mechsim/tmalign_cache.jsonl)
In:   data/raw/comparison/proteins.json                 UniProt accession per gene
      data/raw/downloads/mechsim/alphafold/AF-<acc>-F1-model_v4.pdb.gz
            AlphaFold DB v4 human models (mirror: huggingface.co/datasets/HUBioDataLab/AlphafoldStructures)
      data/raw/downloads/mechsim/rcsb/entities_meta.json
            every RCSB PDB polymer entity mapped to one of our UniProt accessions, fetched from the RCSB
            Search API (all polymer entities whose reference_sequence_identifiers include the accession)
            and the RCSB Data API GraphQL (uniprot_ids, sample length, resolution, method, release date)
Out:  data/raw/comparison/structures.json   per gene: PDB entries (all codes), best-resolution and longest
                                            experimental entity, AlphaFold model id, mean pLDDT, model coverage
      data/raw/comparison/tmalign.json      per pair: TM-score normalised by each chain (pLDDT >= 70 residues)

Why AlphaFold for the comparison: experimental PDB entries cover different fragments of each protein
(a single domain here, a cryo-EM complex there), so they are not comparable across 188 proteins. The
AlphaFold model gives one full-length, uniformly built structure per protein; residues with pLDDT < 70
(disordered or low-confidence) are dropped before alignment. TM-score >= 0.5 (normalised by the
shorter chain) means the two proteins share a fold; ~0.17 is the level of unrelated proteins.
Caveat: proteins longer than 2,700 residues are split into fragments by AlphaFold DB; only fragment F1
(residues 1-1,400) is compared for them, which `structures.json` flags as a partial model.
"""
from __future__ import annotations

import gzip
import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from dcommon import DOWNLOADS, ROOT, TODAY, read_json, write_json

IN = ROOT / "data" / "raw" / "comparison"
AF = DOWNLOADS / "mechsim" / "alphafold"
CACHE = DOWNLOADS / "mechsim" / "tmalign_cache.jsonl"
PLDDT_MIN = 70.0
THREE = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E", "GLY": "G",
         "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S",
         "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}


def load_model(acc):
    path = AF / f"AF-{acc}-F1-model_v4.pdb.gz"
    xyz, seq, full, plddt = [], [], [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("ATOM") and line[12:16].strip() == "CA":
                b = float(line[60:66])
                aa = THREE.get(line[17:20], "X")
                full.append(aa)
                plddt.append(b)
                if b >= PLDDT_MIN:
                    xyz.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
                    seq.append(aa)
    return np.array(xyz), "".join(seq), "".join(full), plddt


_MODELS = {}


def _init(models):
    global _MODELS
    _MODELS = models


def _align(pair):
    from tmtools import tm_align
    a, b = pair
    xa, sa = _MODELS[a]
    xb, sb = _MODELS[b]
    r = tm_align(xa, xb, sa, sb)
    return a, b, round(float(r.tm_norm_chain1), 4), round(float(r.tm_norm_chain2), 4), round(float(r.rmsd), 2)


def inventory(prot):
    meta = read_json(DOWNLOADS / "mechsim" / "rcsb" / "entities_meta.json")
    by_acc = {}
    for e in meta.values():
        info = (e.get("entry") or {}).get("rcsb_entry_info") or {}
        res = info.get("resolution_combined") or [None]
        rec = {"entity": e["rcsb_id"], "entry": e["rcsb_id"].split("_")[0],
               "length": (e.get("entity_poly") or {}).get("rcsb_sample_sequence_length"),
               "resolution": res[0], "method": info.get("experimental_method"),
               "released": (((e.get("entry") or {}).get("rcsb_accession_info") or {}).get("initial_release_date") or "")[:10]}
        for acc in (e.get("rcsb_polymer_entity_container_identifiers") or {}).get("uniprot_ids") or []:
            by_acc.setdefault(acc, []).append(rec)
    return by_acc


def main():
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else os.cpu_count() or 2
    prot = read_json(IN / "proteins.json")["genes"]
    entities = read_json(IN / "entities.json")["entities"]
    genes = [e["gene"] for e in entities]
    atlas = {e["gene"] for e in entities if e["kind"] == "atlas"}
    by_acc = inventory(prot)

    models, structures = {}, {}
    for g in genes:
        acc = prot[g].get("uniprot")
        xyz, seq, full, plddt = load_model(acc)
        models[g] = (xyz, seq)
        length = len(prot[g].get("sequence") or full)
        entries = sorted(by_acc.get(acc, []), key=lambda r: (r["resolution"] is None, r["resolution"] or 99))
        exp = [r for r in entries if r["resolution"] is not None or r["method"] == "NMR"]
        best = exp[0] if exp else None
        longest = max(entries, key=lambda r: r["length"] or 0) if entries else None
        structures[g] = {
            "uniprot": acc,
            "pdb_entries": sorted({r["entry"] for r in entries}),
            "n_pdb_entries": len({r["entry"] for r in entries}),
            "methods": dict(sorted({m: sum(1 for r in entries if r["method"] == m) for m in {r["method"] for r in entries}}.items())),
            "best_resolution": best,
            "longest_construct": longest,
            "alphafold": {"id": f"AF-{acc}-F1", "url": f"https://alphafold.ebi.ac.uk/entry/{acc}",
                          "residues_modelled": len(full), "residues_plddt70": len(seq),
                          "mean_plddt": round(float(np.mean(plddt)), 1),
                          "partial_model": len(full) < length},
            "sequence_from_model": full,
        }
    write_json(IN / "structures.json", {
        "source": "RCSB PDB Search + Data API (GraphQL), AlphaFold DB v4 (HUBioDataLab mirror)",
        "retrieved": TODAY, "plddt_min": PLDDT_MIN, "genes": structures}, compact=True)
    print(f"structures.json: {sum(s['n_pdb_entries'] for s in structures.values())} PDB entries over "
          f"{sum(1 for s in structures.values() if s['n_pdb_entries'])} / {len(structures)} proteins")

    done = {}
    if CACHE.exists():
        for line in CACHE.read_text().splitlines():
            a, b, t1, t2, rmsd = json.loads(line)
            done[(a, b)] = (t1, t2, rmsd)
    pairs = [p for p in itertools.combinations(sorted(genes), 2) if p not in done]
    # atlas pairs first, then pairs touching an atlas gene, then the rest; small proteins before large ones
    pairs.sort(key=lambda p: (-(p[0] in atlas) - (p[1] in atlas), len(models[p[0]][1]) * len(models[p[1]][1])))
    print(f"TM-align: {len(done)} cached, {len(pairs)} to go on {workers} workers")
    with CACHE.open("a") as out, ProcessPoolExecutor(workers, initializer=_init, initargs=(models,)) as pool:
        futs = [pool.submit(_align, p) for p in pairs]
        for k, f in enumerate(as_completed(futs)):
            a, b, t1, t2, rmsd = f.result()
            done[(a, b)] = (t1, t2, rmsd)
            out.write(json.dumps([a, b, t1, t2, rmsd]) + "\n")
            if k % 500 == 0:
                out.flush()
                print(f"  {k}/{len(pairs)}", flush=True)
    write_json(IN / "tmalign.json", {
        "method": "TM-align (tmtools) on AlphaFold DB v4 models, CA atoms with pLDDT >= 70",
        "fields": ["gene_a", "gene_b", "tm_norm_a", "tm_norm_b", "rmsd"],
        "pairs": [[a, b, *v] for (a, b), v in sorted(done.items())]}, compact=True)
    print(f"tmalign.json: {len(done)} pairs")


if __name__ == "__main__":
    main()
