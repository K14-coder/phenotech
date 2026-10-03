"""Which clinical entities belong under each gene-defined umbrella disease.

Every OMIM id below is taken from a Monarch v3 OMIM causal gene-to-disease edge stored in
data/raw/families/rasopathy/diseases.json (build.py asserts this). Inclusion is a curation
decision: GERMLINE Mendelian entities only. Somatic cancers (e.g. KRAS lung cancer, BRAF
colorectal cancer), mosaic/somatic entities (e.g. HRAS epidermal nevus, KRAS AVM of the brain,
MAP2K1 melorheostosis) and JMML (somatic, or a complication) are excluded from subtypes and
from the HPO profile, and listed in attrs.excluded_entities instead.
"""
from __future__ import annotations

GERMLINE_OMIM = {
    "PTPN11": ["163950", "151100", "156250"],     # NS1, LEOPARD/NSML1, metachondromatosis
    "SOS1": ["610733", "135300"],                 # NS4, gingival fibromatosis 1
    "RAF1": ["611553", "611554", "615916"],       # NS5, LEOPARD/NSML2, dilated cardiomyopathy 1NN
    "BRAF": ["115150", "613706", "613707"],       # CFC1, NS7, LEOPARD/NSML3
    "KRAS": ["609942", "615278"],                 # NS3, CFC2
    "HRAS": ["218040"],                           # Costello syndrome
    "NF1": ["162200", "601321", "193520", "162210"],  # NF1, NF-Noonan, Watson, familial spinal NF
    "MAP2K1": ["615279"],                         # CFC3
    "SHOC2": ["607721"],                          # NS-like disorder with loose anagen hair 1
    "CBL": ["613563"],                            # NS-like disorder with or without JMML
    "RIT1": ["615355"],                           # NS8
    "LZTR1": ["616564", "605275", "615670"],      # NS10 (dominant), NS2 (recessive), schwannomatosis 2
}

# Syndrome keys used to map ClinicalTrials.gov condition names / org scopes to umbrellas.
# Derived from the OMIM entity names above (checked against diseases.json in build.py).
SYNDROME_KEYS = {
    "noonan": ["PTPN11", "SOS1", "RAF1", "BRAF", "KRAS", "RIT1", "LZTR1"],
    "nsml": ["PTPN11", "RAF1", "BRAF"],
    "cfc": ["BRAF", "KRAS", "MAP2K1"],
    "costello": ["HRAS"],
    "nf1": ["NF1"],
    "noonan_like": ["SHOC2", "CBL"],
}


def orpha_gene_specific(drec: dict) -> list[str]:
    """Orphanet entities that are germline disease-causing AND gene-specific (1 associated gene)."""
    out = []
    for code, a in (drec.get("orphanet_associations") or {}).items():
        at = a.get("association_type") or ""
        if a.get("found") and at.startswith("Disease-causing germline") and a.get("n_genes_associated") == 1:
            out.append(code)
    return sorted(out)
