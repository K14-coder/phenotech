"""Fetch recent (2018+) disease-oriented PubMed records per slice gene, with author affiliations.

NCBI E-utilities is shared with another agent: <= 2 requests/s, tool=rare-disease-atlas,
NO email parameter, exponential backoff on 429 (see common.http).
E-mail addresses embedded in affiliation strings are redacted before saving.
Re-runnable: overwrites data/raw/community/pubmed/<GENE>.esearch.json and <GENE>.efetch.xml.
Usage:  python3 pipeline/community/fetch_pubmed.py
"""
from __future__ import annotations

import json
import time
import urllib.parse

from common import RAW, http, redact_emails, today, write_json

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "rare-disease-atlas"
PAUSE = 0.6  # seconds between requests (<= 2 req/s)

# Disease-context filter: keeps human-disorder papers, drops pure biomarker / association studies.
DIS = ('("de novo"[tiab] OR neurodevelopmental[tiab] OR "intellectual disability"[tiab] OR '
       'encephalopath*[tiab] OR "developmental delay"[tiab] OR myasthenic[tiab] OR '
       '"pathogenic variant"[tiab] OR "pathogenic variants"[tiab] OR "missense variant"[tiab] OR '
       '"missense variants"[tiab] OR epileptic[tiab] OR epilepsy[tiab] OR seizures[tiab] OR '
       'patients[tiab] OR "Baker-Gordon"[tiab] OR SNAREopath*[tiab] OR haploinsufficien*[tiab])')
NOT_ASSOC = ('(alzheimer*[tiab] OR botulinum[tiab] OR "cerebrospinal fluid"[tiab] OR schizophreni*[tiab] '
             'OR ADHD[tiab] OR "attention deficit"[tiab] OR polymorphism*[tiab] OR amyotrophic[tiab] '
             'OR "nephrogenic systemic fibrosis"[tiab] OR cancer[tiab] OR tumor[tiab] OR tumour[tiab])')

QUERIES = {
    "STXBP1": f'(STXBP1[tiab] OR "Munc18-1"[tiab]) AND {DIS}',
    "SYT1": f'(SYT1[tiab] OR "synaptotagmin-1"[tiab] OR "synaptotagmin 1"[tiab] OR "Baker-Gordon"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "SNAP25": f'(SNAP25[tiab] OR "SNAP-25"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "VAMP2": f'(VAMP2[tiab] OR "synaptobrevin-2"[tiab] OR "synaptobrevin 2"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "STX1B": f'(STX1B[tiab] OR "syntaxin-1B"[tiab] OR "syntaxin 1B"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "SYT2": f'(SYT2[tiab] OR "synaptotagmin 2"[tiab] OR "synaptotagmin-2"[tiab]) AND (myasthenic[tiab] OR neuropathy[tiab] OR patients[tiab] OR "pathogenic variant"[tiab] OR "pathogenic variants"[tiab] OR "de novo"[tiab] OR neuromuscular[tiab]) NOT {NOT_ASSOC}',
    "CPLX1": f'(CPLX1[tiab] OR "complexin 1"[tiab] OR "complexin-1"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "UNC13A": f'(UNC13A[tiab] OR "Munc13-1"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "STX1A": f'(STX1A[tiab] OR "syntaxin-1A"[tiab] OR "syntaxin 1A"[tiab]) AND {DIS} NOT {NOT_ASSOC}',
    "NSF": f'("N-ethylmaleimide sensitive factor"[tiab] OR "N-ethylmaleimide-sensitive factor"[tiab] OR (NSF[tiab] AND gene[tiab])) AND {DIS} NOT {NOT_ASSOC}',
    "SLC6A1": f'(SLC6A1[tiab] OR (("GAT-1"[tiab] OR GAT1[tiab]) AND ("de novo"[tiab] OR variants[tiab]) AND (epilepsy[tiab] OR neurodevelopmental[tiab]))) AND {DIS}',
}


def eutil(name: str, params: dict) -> bytes:
    params = {**params, "tool": TOOL}
    url = f"{EUTILS}/{name}.fcgi?{urllib.parse.urlencode(params)}"
    status, body, _ = http(url)
    time.sleep(PAUSE)
    if status != 200:
        raise RuntimeError(f"{status} {url}: {body[:200]!r}")
    return body


def main():
    out = RAW / "pubmed"
    out.mkdir(parents=True, exist_ok=True)
    for gene, q in QUERIES.items():
        es = json.loads(eutil("esearch", {"db": "pubmed", "term": q, "retmax": 200, "retmode": "json",
                                          "datetype": "pdat", "mindate": "2018", "maxdate": "2026",
                                          "sort": "pub_date"}))
        ids = es["esearchresult"].get("idlist", [])
        write_json(out / f"{gene}.esearch.json", {"gene": gene, "query": q, "retrieved": today(),
                                                    "count": es["esearchresult"].get("count"), "ids": ids})
        xml_parts = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            xml_parts.append(eutil("efetch", {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"}).decode("utf-8"))
        (out / f"{gene}.efetch.xml").write_text(redact_emails("\n<!-- batch -->\n".join(xml_parts)))
        print(f"{gene}: count={es['esearchresult'].get('count')} fetched={len(ids)}")


if __name__ == "__main__":
    main()
