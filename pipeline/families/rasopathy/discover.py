"""Literature discovery for the RASopathy claims: runs the PubMed searches below, stores every
hit's abstract locally (pubmed.py) and logs each query (data/raw/families/rasopathy/pubmed_searches.json).
Curation then picks PMIDs from these stored records only.

Run:  python3 pipeline/families/rasopathy/discover.py [group ...]
"""
from __future__ import annotations

import sys

import pubmed

SEARCHES = {
    "family": [
        'RASopathies[ti] AND Tidyman[au]',
        'RASopathies[ti] AND Rauen KA[au]',
        'RASopathy[ti] AND Tajan M[au]',
        'RASopathy[tiab] AND ClinGen[tiab] AND gene curation[tiab]',
    ],
    "ptpn11": [
        'PTPN11[ti] AND Noonan[ti] AND Tartaglia M[au] AND 2001[dp]',
        'PTPN11[tiab] AND Tartaglia M[au] AND functional consequences[ti]',
        'LEOPARD[ti] AND Kontaridis MI[au]',
        'LEOPARD syndrome[tiab] AND SHP2[tiab] AND catalytic activity[tiab]',
        'metachondromatosis[ti] AND PTPN11[tiab]',
        'rapamycin[tiab] AND LEOPARD[tiab] AND cardiomyopathy[tiab]',
    ],
    "sos1_raf1": [
        'SOS1[ti] AND Noonan[ti] AND 2007[dp]',
        'RAF1[ti] AND Noonan[ti] AND 2007[dp]',
    ],
    "braf_mek_kras_hras": [
        'cardio-facio-cutaneous[ti] AND 2006[dp] AND (BRAF[tiab] OR MEK1[tiab])',
        'KRAS[ti] AND Noonan[ti] AND Schubbert S[au]',
        'HRAS[ti] AND Costello[ti] AND Aoki Y[au]',
    ],
    "nf1": [
        'neurofibromin[tiab] AND GTPase-activating[tiab] AND Ras[tiab] AND neurofibromatosis type 1[tiab] AND review[pt]',
        'neurofibromatosis-Noonan syndrome[ti] AND NF1[tiab]',
    ],
    "shoc2_cbl_rit1_lztr1": [
        'SHOC2[ti] AND Cordeddu V[au]',
        'CBL[ti] AND Noonan[tiab] AND 2010[dp]',
        'RIT1[ti] AND Noonan[ti] AND Aoki Y[au]',
        'LZTR1[ti] AND RAS[ti] AND ubiquitination[ti]',
        'LZTR1[ti] AND Noonan[tiab] AND (dominant[tiab] OR recessive[tiab] OR biallelic[tiab])',
    ],
    "therapy": [
        'selumetinib[ti] AND plexiform[ti] AND Gross AM[au]',
        'selumetinib[ti] AND plexiform[ti] AND Dombi E[au]',
        'mirdametinib[ti] AND plexiform[tiab]',
        'Noonan[tiab] AND MEK[tiab] AND hypertrophic cardiomyopathy[tiab] AND trametinib[tiab]',
        'trametinib[tiab] AND (RASopathy[tiab] OR RASopathies[tiab] OR Noonan[tiab]) AND (lymphatic[tiab] OR chylothorax[tiab] OR chylous[tiab])',
        'Raf1 L613V[tiab] AND MEK[tiab]',
        'MEK inhibitor[tiab] AND (Costello syndrome[tiab] OR cardiofaciocutaneous[tiab] OR cardio-facio-cutaneous[tiab])',
        '(simvastatin[ti] OR lovastatin[ti]) AND neurofibromatosis[ti] AND (randomized[tiab] OR trial[tiab])',
        'tipifarnib[ti] AND neurofibromatosis[ti]',
    ],
}


def main():
    groups = sys.argv[1:] or list(SEARCHES)
    for g in groups:
        for term in SEARCHES[g]:
            print(f"\n### [{g}] {term}")
            ids = pubmed.esearch(term, retmax=8)
            recs = pubmed.fetch_pmids(ids)
            for p in ids:
                r = recs.get(p)
                if r:
                    print(f"  {p} {r['year']} {r.get('journal','')[:30]} | {r['title'][:140]}")


if __name__ == "__main__":
    main()
