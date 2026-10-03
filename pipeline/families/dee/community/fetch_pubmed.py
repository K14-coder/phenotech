"""Fetch recent (2018+) gene-focused human-disorder PubMed records per DEE gene, with affiliations.

Uses pipeline/biology/common.py eutils(): shared cross-process throttle (<= 2 req/s),
tool=rare-disease-atlas, NO email param, backoff on 429. E-mails in affiliations are redacted.
Stores data/raw/families/dee/community/pubmed/<GENE>.esearch.json and <GENE>.efetch.xml.
Usage:  python3 fetch_pubmed.py [--refresh]
"""
from __future__ import annotations

import json
import sys

from dee_common import PUBMED, ROOT, redact_emails, today, write_json

sys.path.insert(0, str(ROOT / "pipeline" / "biology"))
from common import eutils  # noqa: E402  (pipeline/biology/common.py)

DIS = ('("de novo"[tiab] OR neurodevelopmental[tiab] OR "intellectual disability"[tiab] OR '
       'encephalopath*[tiab] OR "developmental delay"[tiab] OR "pathogenic variant"[tiab] OR '
       '"pathogenic variants"[tiab] OR epileptic[tiab] OR epilepsy[tiab] OR seizures[tiab] OR patients[tiab] OR '
       'children[tiab] OR cohort[tiab])')
QUERIES = {
    "SCN1A": f'(SCN1A[tiab]) AND ({DIS} OR Dravet[tiab])',
    "SCN2A": f'(SCN2A[tiab]) AND {DIS}',
    "SCN8A": f'(SCN8A[tiab]) AND {DIS}',
    "KCNQ2": f'(KCNQ2[tiab]) AND {DIS}',
    "KCNT1": f'(KCNT1[tiab]) AND {DIS}',
    "CACNA1A": f'(CACNA1A[tiab]) AND ({DIS} OR "episodic ataxia"[tiab] OR "hemiplegic migraine"[tiab])',
    "GRIN2B": f'(GRIN2B[tiab]) AND {DIS}',
    "CDKL5": f'(CDKL5[tiab]) AND ({DIS} OR "deficiency disorder"[tiab])',
    "SYNGAP1": f'(SYNGAP1[tiab]) AND {DIS}',
    "SLC2A1": f'(SLC2A1[tiab] OR "GLUT1 deficiency"[tiab] OR "Glut1 deficiency"[tiab] OR "GLUT1DS"[tiab]) AND ({DIS} OR "ketogenic diet"[tiab])',
}


def main():
    refresh = "--refresh" in sys.argv
    PUBMED.mkdir(parents=True, exist_ok=True)
    for gene, q in QUERIES.items():
        if (PUBMED / f"{gene}.efetch.xml").exists() and not refresh:
            continue
        es = json.loads(eutils("esearch.fcgi", {"db": "pubmed", "term": q, "retmax": 200, "retmode": "json",
                                                 "datetype": "pdat", "mindate": "2018", "maxdate": "2026",
                                                 "sort": "pub_date"}))
        ids = es["esearchresult"].get("idlist", [])
        write_json(PUBMED / f"{gene}.esearch.json", {"gene": gene, "query": q, "retrieved": today(),
                                                      "count": es["esearchresult"].get("count"), "ids": ids})
        parts = []
        for i in range(0, len(ids), 100):
            parts.append(eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids[i:i + 100]),
                                                "retmode": "xml"}).decode("utf-8"))
        (PUBMED / f"{gene}.efetch.xml").write_text(redact_emails("\n<!-- batch -->\n".join(parts)))
        print(f"{gene}: count={es['esearchresult'].get('count')} fetched={len(ids)}", file=sys.stderr)


if __name__ == "__main__":
    main()
