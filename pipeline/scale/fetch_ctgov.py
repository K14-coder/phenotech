"""ClinicalTrials.gov API v2 at scale: one query per disease name (query.cond) and per gene symbol
(query.term), pageSize 100, fields limited to what the breadth layer needs. 4 requests in parallel,
exponential backoff on 429/5xx (common.http). Re-runnable and resumable:

  data/raw/scale/ctgov/queries.jsonl            one line per finished query {key, param, value, total, pages, ncts}
  data/raw/scale/ctgov/studies_*.jsonl.gz       compact study records (deduplicated by NCT id)

Adaptive depth: if a query has > 100 hits and >= 30 of the first 100 already pass the precision filter
for the queried term, up to MAX_PAGES pages are fetched (so big diseases get real counts).

Usage: python3 fetch_ctgov.py [--limit N]
"""
from __future__ import annotations

import concurrent.futures as cf
import gzip
import json
import re
import sys
import threading
import time
import urllib.parse

from common import OUT, RAW, http, norm_text, read_json, today

BASE = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,BriefTitle,OverallStatus,Phase,StudyType,Condition,Keyword,InterventionName,"
          "InterventionType,LeadSponsorName,LeadSponsorClass,CollaboratorName,CollaboratorClass,"
          "StartDate,EnrollmentCount")
DIR = RAW / "ctgov"
QLOG = DIR / "queries.jsonl"
MAX_PAGES = 10
WORKERS = 4


def compact(s: dict) -> dict:
    p = s.get("protocolSection", {})
    idm, st = p.get("identificationModule", {}), p.get("statusModule", {})
    sp, cm = p.get("sponsorCollaboratorsModule", {}), p.get("conditionsModule", {})
    dm, am = p.get("designModule", {}), p.get("armsInterventionsModule", {})
    lead = sp.get("leadSponsor") or {}
    return {
        "nct": idm.get("nctId"),
        "title": idm.get("briefTitle") or "",
        "status": st.get("overallStatus"),
        "start": (st.get("startDateStruct") or {}).get("date"),
        "type": dm.get("studyType"),
        "phases": dm.get("phases") or [],
        "enrollment": (dm.get("enrollmentInfo") or {}).get("count"),
        "conditions": cm.get("conditions") or [],
        "keywords": cm.get("keywords") or [],
        "interventions": [{"type": i.get("type"), "name": i.get("name")} for i in (am.get("interventions") or [])][:12],
        "lead": {"name": lead.get("name"), "class": lead.get("class")},
        "collaborators": [{"name": c.get("name"), "class": c.get("class")} for c in (sp.get("collaborators") or [])],
    }


def passes(study: dict, param: str, value: str) -> bool:
    """Precision filter for the queried term only (used to decide whether to page deeper)."""
    fields = study["conditions"] + study["keywords"] + [study["title"]]
    if param == "query.term":  # gene symbol: case-sensitive whole token
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])")
        return any(pat.search(f) for f in fields)
    nv = norm_text(value)
    return any(f" {nv} " in f" {norm_text(f)} " for f in fields)


def run_query(param: str, value: str) -> tuple[dict, list[dict]]:
    studies, token, pages, total = [], None, 0, None
    while True:
        q = {param: value, "pageSize": 100, "fields": FIELDS, "format": "json"}
        if pages == 0:
            q["countTotal"] = "true"
        if token:
            q["pageToken"] = token
        st, body, _ = http(f"{BASE}?{urllib.parse.urlencode(q)}", headers={"Accept": "application/json"},
                           retries=6, backoff=3.0)
        if st != 200:
            return {"param": param, "value": value, "error": st, "retrieved": today()}, []
        data = json.loads(body)
        if pages == 0:
            total = data.get("totalCount", 0)
        batch = [compact(s) for s in data.get("studies", [])]
        studies.extend(batch)
        pages += 1
        token = data.get("nextPageToken")
        if not token or pages >= MAX_PAGES:
            break
        if pages == 1 and sum(passes(s, param, value) for s in batch) < 30:
            break
    rec = {"param": param, "value": value, "total": total, "pages": pages, "n": len(studies),
           "ncts": [s["nct"] for s in studies], "retrieved": today(),
           "capped": bool(token)}
    return rec, studies


def plan_queries(universe: dict) -> list[tuple[str, str, str]]:
    """[(key, param, value)], priority order: ORPHA names, gene symbols, OMIM names."""
    seen, out = set(), []

    def add(param, value):
        key = f"{param}|{norm_text(value) if param == 'query.cond' else value}"
        if key not in seen and value.strip():
            seen.add(key)
            out.append((key, param, value))

    ds = universe["diseases"]
    for did in sorted(ds):
        if did.startswith("ORPHA:"):
            add("query.cond", ds[did]["name"])
    for g in sorted(universe["genes"]):
        add("query.term", g)
    for did in sorted(ds):
        if did.startswith("OMIM:"):
            add("query.cond", ds[did]["name"])
    return out


def load_done() -> set:
    done = set()
    if QLOG.exists():
        for line in QLOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if "error" not in r:
                done.add(r["key"])
    return done


def load_known_ncts() -> set:
    known = set()
    for p in sorted(DIR.glob("studies_*.jsonl.gz")):
        with gzip.open(p, "rt") as f:
            for line in f:
                known.add(json.loads(line)["nct"])
    return known


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    universe = read_json(OUT / "universe.json")
    queries = plan_queries(universe)
    DIR.mkdir(parents=True, exist_ok=True)
    done = load_done()
    known = load_known_ncts()
    todo = [q for q in queries if q[0] not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(queries)} queries planned, {len(done)} done, {len(todo)} to run; {len(known)} studies cached",
          flush=True)
    chunk_id = len(list(DIR.glob("studies_*.jsonl.gz")))
    pending_studies, lock, t0, n_done = [], threading.Lock(), time.time(), 0

    def flush():
        nonlocal chunk_id, pending_studies
        if not pending_studies:
            return
        with gzip.open(DIR / f"studies_{chunk_id:05d}.jsonl.gz", "wt") as f:
            for s in pending_studies:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        chunk_id += 1
        pending_studies = []

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex, QLOG.open("a") as qlog:
        futs = {ex.submit(run_query, p, v): k for k, p, v in todo}
        for fut in cf.as_completed(futs):
            key = futs[fut]
            try:
                rec, studies = fut.result()
            except Exception as e:
                rec, studies = {"error": str(e)[:200]}, []
            rec["key"] = key
            qlog.write(json.dumps(rec, ensure_ascii=False) + "\n")
            with lock:
                for s in studies:
                    if s["nct"] and s["nct"] not in known:
                        known.add(s["nct"])
                        pending_studies.append(s)
                n_done += 1
                if n_done % 250 == 0:
                    qlog.flush()
                    flush()
                    rate = n_done / (time.time() - t0)
                    print(f"  {n_done}/{len(todo)} queries, {len(known)} studies, {rate:.1f} q/s", flush=True)
        flush()
    print(f"done: {n_done} queries in {time.time() - t0:.0f}s, {len(known)} unique studies", flush=True)


if __name__ == "__main__":
    main()
