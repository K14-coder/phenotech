"""Research groups per RASopathy gene from PubMed (adapted from pipeline/community/fetch_pubmed.py):
recent (2018+) papers that tie the gene to the germline disorder; the senior (last) author of each
paper is the "group". Professional information only (name, affiliation, ORCID if in the PubMed
record); e-mail addresses are redacted before anything is saved.

Run:  python3 pipeline/families/rasopathy/fetch_authors.py
Out:  data/raw/families/rasopathy/authors/<GENE>.esearch.json; every article stored as
      data/raw/families/rasopathy/pubmed/<PMID>.json (so works_on quotes are verifiable)
NCBI etiquette: shared throttle (pipeline/biology/common.py), tool=rare-disease-atlas, no email.
"""
from __future__ import annotations

import json

import pubmed
from ras_common import GENES, RAW, TODAY, eutils, write_json

RAS_CTX = ('(Noonan[tiab] OR RASopath*[tiab] OR Costello[tiab] OR cardiofaciocutaneous[tiab] OR '
           '"cardio-facio-cutaneous"[tiab] OR "multiple lentigines"[tiab] OR LEOPARD[tiab] OR '
           '"loose anagen"[tiab] OR Mazzanti[tiab] OR metachondromatosis[tiab] OR schwannomatosis[tiab])')
NOT_ONC = ('(cancer[ti] OR carcinoma[ti] OR tumor[ti] OR tumour[ti] OR leukemia[ti] OR leukaemia[ti] '
           'OR melanoma[ti] OR glioma[ti] OR lymphoma[ti] OR adenocarcinoma[ti] OR sarcoma[ti])')
QUERIES = {g: f"{g}[tiab] AND {RAS_CTX} NOT {NOT_ONC}" for g in GENES if g != "NF1"}
QUERIES["NF1"] = ('("neurofibromatosis type 1"[ti] OR "neurofibromatosis 1"[ti]) AND NF1[tiab] AND '
                  '(germline[tiab] OR variant*[tiab] OR mutation*[tiab]) NOT ' + NOT_ONC)
OUT = RAW / "authors"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for gene, q in QUERIES.items():
        res = json.loads(eutils("esearch.fcgi", {"db": "pubmed", "term": q, "retmax": 80, "retmode": "json",
                                                 "datetype": "pdat", "mindate": "2018", "maxdate": "2026",
                                                 "sort": "relevance"}))["esearchresult"]
        ids = res.get("idlist", [])
        write_json(OUT / f"{gene}.esearch.json", {"gene": gene, "query": q, "retrieved": TODAY,
                                                  "count": res.get("count"), "ids": ids})
        pubmed.fetch_pmids(ids)
        print(f"{gene}: count={res.get('count')} fetched={len(ids)}")


if __name__ == "__main__":
    main()
