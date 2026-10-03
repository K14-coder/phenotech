"""Population & trial-readiness layer -> data/derived/population/  (stdlib only)

  python3 pipeline/derive/population.py            # uses cached Orphadata XML
  python3 pipeline/derive/population.py --fetch    # (re)download en_product9_prev.xml first

Outputs
  prevalence.json  Orphanet epidemiology (Orphadata product 9) for every ORPHA code, mapped to MONDO
                   (via data/derived/global/index.json) and to the 45 deep-atlas umbrella diseases,
                   with a rough, class-bound "estimated people affected" range (never a count).
  readiness.json   8-component trial-readiness profile for the 45 deep diseases, computed only from
                   data/graph.json; every component lists the evidence edge ids it rests on.
  channels.json    Recruitment channels (registries, natural-history studies, data platforms, networks,
                   patient organisations, recruiting trials) for the 45 deep diseases, from the graph plus
                   the breadth layer (data/derived/scale/{orgs,assets,trials}.json). Organisational
                   channels only: no personal names, e-mails or phone numbers.
"""
from __future__ import annotations

import datetime as dt
import html.parser
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
PREV_XML = DOWNLOADS / "en_product9_prev.xml"
PREV_URL = "https://www.orphadata.com/data/xml/en_product9_prev.xml"
OUT = ROOT / "data" / "derived" / "population"
GRAPH = ROOT / "data" / "graph.json"
INDEX = ROOT / "data" / "derived" / "global" / "index.json"
SCALE = ROOT / "data" / "derived" / "scale"
WEB_DIRS = [ROOT / "data/raw/community/web", ROOT / "data/raw/families/lysosomal/web",
            ROOT / "data/raw/families/rasopathy/web", ROOT / "data/raw/families/dee/community/web"]
TODAY = dt.date.today().isoformat()

POPULATION = {"worldwide": 8.1e9, "europe": 750e6, "us": 335e6}
# Where each area's rate may come from, in order of preference (Orphanet geographic names).
RATE_SOURCES = {"worldwide": ["Worldwide", "Europe"],
                "europe": ["Europe", "Worldwide"],
                "us": ["United States", "Worldwide", "Europe"]}
# Orphanet prevalence classes -> [lower, upper] rate per person. Upper None = open-ended.
CLASS_BOUNDS = {
    "<1 / 1 000 000": (0.0, 1e-6),
    "1-9 / 1 000 000": (1e-6, 9e-6),
    "1-9 / 100 000": (1e-5, 9e-5),
    "1-5 / 10 000": (1e-4, 5e-4),
    "6-9 / 10 000": (6e-4, 9e-4),
    ">1 / 1000": (1e-3, None),
}
METHOD = ("ROUGH ORDER-OF-MAGNITUDE RANGE, NOT A COUNT. people = Orphanet prevalence-class bounds x "
          "population (worldwide 8.1 billion, Europe 750 million, US 335 million). Point prevalence is used "
          "when Orphanet has a usable class; otherwise prevalence at birth is used as a proxy (overestimates "
          "living patients when survival is reduced). A rate recorded for one area is applied to another only "
          "when that area has no record of its own (see rate_from). '<1 / 1 000 000' has lower bound 0; "
          "'>1 / 1000' has no upper bound. Classes 'Unknown' / 'Not yet documented', annual incidence and "
          "case counts are never converted to people.")


def sig(x, n=2):
    if x is None:
        return None
    if x == 0:
        return 0
    from math import floor, log10
    return int(round(x, -int(floor(log10(abs(x)))) + (n - 1)))


# --------------------------------------------------------------------------------------- Orphanet

def fetch():
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(PREV_URL, headers={"User-Agent": "rare-disease-atlas/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        PREV_XML.write_bytes(r.read())


def parse_orphanet():
    root = ET.parse(PREV_XML).getroot()
    meta = {"date": root.get("date"), "version": root.get("version")}
    out = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        recs = []
        for p in d.iter("Prevalence"):
            src = p.findtext("Source") or ""
            vm = p.findtext("ValMoy")
            vm = float(vm) if vm not in (None, "") else None
            rec = {
                "type": p.findtext("PrevalenceType/Name"),
                "qualification": p.findtext("PrevalenceQualification/Name"),
                "class": p.findtext("PrevalenceClass/Name"),
                "area": p.findtext("PrevalenceGeographic/Name"),
                "validation": p.findtext("PrevalenceValidationStatus/Name"),
                "pmids": sorted(set(re.findall(r"(\d+)\[PMID\]", src)), key=int),
                "source": src,
            }
            if vm:  # ValMoy 0.0 means "not given"
                if rec["type"] == "Cases/families":
                    rec["n_reported"] = vm  # number of cases or families reported in the literature
                else:
                    rec["mean_per_100k"] = vm
            recs.append({k: v for k, v in rec.items() if v not in (None, [], "")})
        out[code] = {"orpha": code, "name": d.findtext("Name"),
                     "group": d.findtext("DisorderGroup/Name"),
                     "url": f"https://www.orpha.net/en/disease/detail/{code}", "records": recs}
    return meta, out


def estimate(records):
    """Class-bound people range per area from one ORPHA code's records."""
    usable = [r for r in records if r.get("class") in CLASS_BOUNDS]
    for basis_type, basis in (("Point prevalence", "point prevalence"),
                              ("Prevalence at birth", "prevalence at birth (proxy)")):
        recs = [r for r in usable if r["type"] == basis_type]
        if not recs:
            continue
        # prefer validated records when any exist
        if any(r.get("validation") == "Validated" for r in recs):
            recs = [r for r in recs if r.get("validation") == "Validated"]
        by_area = defaultdict(list)
        for r in recs:
            by_area[r["area"]].append(r)
        est = {"basis": basis}
        for area, chain in RATE_SOURCES.items():
            src = next((a for a in chain if a in by_area), None)
            if not src:
                continue
            classes = sorted({r["class"] for r in by_area[src]}, key=lambda c: CLASS_BOUNDS[c][0])
            lo = min(CLASS_BOUNDS[c][0] for c in classes)
            ups = [CLASS_BOUNDS[c][1] for c in classes]
            hi = None if None in ups else max(ups)
            pop = POPULATION[area]
            e = {"low": sig(lo * pop), "high": sig(hi * pop) if hi is not None else None,
                 "classes": classes, "rate_from": src}
            means = [r["mean_per_100k"] for r in by_area[src] if r.get("mean_per_100k")]
            if means:
                m = sum(means) / len(means)
                e["from_mean_value"] = sig(m / 1e5 * pop)
            est[area] = e
        if len(est) > 1:
            return est
    return None


def fmt_range(e):
    if not e:
        return None
    lo, hi = e["low"], e["high"]
    if hi is None:
        return f"more than ~{lo:,}"
    if lo == 0:
        return f"fewer than ~{hi:,}"
    return f"~{lo:,} to {hi:,}"


# --------------------------------------------------------------------------------------- graph helpers

def load_graph():
    g = json.load(open(GRAPH))
    nodes = {n["id"]: n for n in g["nodes"]}
    return g, nodes


def deep_ids(nodes, index_rows):
    """For each deep disease: MONDO / OMIM / ORPHA ids from xrefs, subtypes and the global index."""
    by_mondo = {r[0]: r for r in index_rows}
    by_omim, by_orpha = defaultdict(list), defaultdict(list)
    for r in index_rows:
        for o in filter(None, r[3].split(",")):
            by_omim[o].append(r)
        for o in filter(None, r[4].split(",")):
            by_orpha[o].append(r)
    out = {}
    for n in nodes.values():
        if n["type"] != "disease":
            continue
        x = n.get("xrefs", {})
        as_list = lambda v: v if isinstance(v, list) else ([v] if v else [])
        mondo, omim, orpha = set(as_list(x.get("MONDO"))), set(as_list(x.get("OMIM"))), set(as_list(x.get("ORPHA")))
        for s in n.get("attrs", {}).get("subtypes", []) or []:
            mondo |= set(as_list(s.get("MONDO")))
            omim |= set(as_list(s.get("OMIM")))
            orpha |= set(as_list(s.get("ORPHA")))
        # rows flagged as this atlas disease in the global index
        for r in index_rows:
            if r[8] == n["id"]:
                mondo.add(r[0])
        for m in list(mondo):
            r = by_mondo.get(m)
            if r:
                omim |= set(filter(None, r[3].split(",")))
                orpha |= set(filter(None, r[4].split(",")))
        gene = n.get("attrs", {}).get("gene") or n["id"].split(":", 1)[1]
        own_orpha = set(orpha)
        orpha_genes = {}
        for o in orpha:
            orpha_genes[o] = sorted({gn for r in by_orpha.get(o, []) for gn in filter(None, r[5].split(","))})
        # related clinical entities: any index row naming this gene (context only, never aggregated)
        related = set()
        for r in index_rows:
            if gene in r[5].split(","):
                for o in filter(None, r[4].split(",")):
                    if o not in own_orpha:
                        related.add(o)
                        orpha_genes[o] = sorted({gn for rr in by_orpha.get(o, []) for gn in filter(None, rr[5].split(","))})
        out[n["id"]] = {"label": n["label"], "gene": gene,
                        "mondo": sorted(mondo), "omim": sorted(omim), "orpha": sorted(orpha, key=int),
                        "related_orpha": sorted(related, key=int), "orpha_genes": orpha_genes}
    return out


# --------------------------------------------------------------------------------------- prevalence

def build_prevalence(index_rows, deep):
    meta, orpha = parse_orphanet()
    for o in orpha.values():
        o["estimate"] = estimate(o["records"])
    mondo_map = {}
    for r in index_rows:
        codes = [c for c in filter(None, r[4].split(",")) if c in orpha]
        if codes:
            mondo_map[r[0]] = codes
    n_mondo = sum(1 for r in index_rows if r[0].startswith("MONDO:"))
    n_mondo_prev = sum(1 for k in mondo_map if k.startswith("MONDO:"))
    n_mondo_est = sum(1 for k, cs in mondo_map.items() if k.startswith("MONDO:") and any(orpha[c]["estimate"] for c in cs))

    deep_out = {}
    for did, d in sorted(deep.items()):
        codes = [c for c in d["orpha"] if c in orpha]
        entries = []
        for c in codes + [c for c in d["related_orpha"] if c in orpha]:
            o = orpha[c]
            genes = d["orpha_genes"].get(c, [])
            if c in d["orpha"]:
                scope = "gene_specific" if len(genes) <= 2 else "shared_clinical_entity"
            else:
                scope = "related_clinical_entity"
            entries.append({"orpha": c, "name": o["name"], "group": o["group"], "url": o["url"],
                            "scope": scope, "genes": genes, "in_aggregate": scope == "gene_specific" and bool(o["estimate"]),
                            "records": o["records"], "estimate": o["estimate"]})
        # Umbrella range across distinct gene-specific ORPHA entities: low = largest single low,
        # high = sum of highs (entities may overlap, so this is a ceiling).
        agg = {}
        ests = [e["estimate"] for e in entries if e["in_aggregate"]]
        for area in POPULATION:
            parts = [e[area] for e in ests if area in e]
            if not parts:
                continue
            hi = None if any(p["high"] is None for p in parts) else sig(sum(p["high"] for p in parts))
            agg[area] = {"low": max(p["low"] for p in parts), "high": hi, "n_entities": len(parts)}
            agg[area]["text"] = fmt_range(agg[area])
        bases = sorted({e["basis"] for e in ests})
        areas = sorted({r["area"] for e in entries if e["scope"] != "related_clinical_entity"
                        for r in e["records"] if r.get("area")})
        deep_out[did] = {"label": d["label"], "mondo": d["mondo"], "orpha_codes": d["orpha"],
                         "orpha_with_prevalence": codes, "geographic_areas": areas,
                         "estimated_people": agg or None, "estimate_basis": bases,
                         "entities": entries}
    n_deep = sum(1 for v in deep_out.values() if v["orpha_with_prevalence"])
    n_deep_any = sum(1 for v in deep_out.values() if v["entities"])
    n_deep_est = sum(1 for v in deep_out.values() if v["estimated_people"])
    return {
        "meta": {
            "generated": TODAY,
            "source": {"name": "Orphadata product 9: Epidemiology (en_product9_prev.xml)", "url": PREV_URL,
                       "orphadata_date": meta["date"], "version": meta["version"], "licence": "CC-BY-4.0",
                       "local_copy": "data/raw/downloads/en_product9_prev.xml"},
            "method": METHOD,
            "population": POPULATION,
            "class_bounds_per_person": {k: list(v) for k, v in CLASS_BOUNDS.items()},
            "mean_per_100k": "Orphanet ValMoy: mean prevalence/incidence per 100,000 when a value was published.",
            "n_reported": "For type 'Cases/families': number of cases or families reported in the literature.",
            "mondo_mapping": "ORPHA codes listed on data/derived/global/index.json rows (MONDO equivalentTo xrefs).",
            "deep_aggregate": ("Umbrella range across the disease's gene-specific ORPHA entities only (entity listed on the "
                               "graph node's xrefs/subtypes AND linked to <= 2 genes in the global index): low = largest "
                               "single low, high = sum of highs (entities can overlap, so high is a ceiling). "
                               "shared_clinical_entity (e.g. Lennox-Gastaut, Noonan syndrome) and related_clinical_entity "
                               "(any index row naming the gene) are shown with their own prevalence for context but are "
                               "never added in, because their prevalence covers patients with other genes."),
            "files": {"prevalence.json": "meta + deep (45 diseases) + mondo -> ORPHA codes",
                      "prevalence_orpha.json": "all ORPHA codes: records + estimate"},
            "counts": {"orpha_codes": len(orpha),
                       "orpha_with_people_estimate": sum(1 for o in orpha.values() if o["estimate"]),
                       "index_rows_with_prevalence": len(mondo_map),
                       "mondo_diseases": n_mondo, "mondo_with_prevalence": n_mondo_prev,
                       "mondo_with_people_estimate": n_mondo_est,
                       "deep_diseases": len(deep_out), "deep_with_prevalence": n_deep, "deep_with_any_prevalence_incl_related": n_deep_any,
                       "deep_with_people_estimate": n_deep_est},
        },
        "deep": deep_out,
        "mondo": mondo_map,
        "orpha": orpha,
    }


# --------------------------------------------------------------------------------------- readiness

PHASE_RANK = {"EARLY_PHASE1": 0.5, "PHASE1": 1, "PHASE1/PHASE2": 1.5, "PHASE2": 2, "PHASE2/PHASE3": 2.5,
              "PHASE3": 3, "PHASE4": 4}
UMBRELLA_SCOPE = re.compile(r"umbrella|multi-gene|multi-disease|consortium|coalition|neuromuscular", re.I)
OUTCOME_WORDS = re.compile(r"outcome|endpoint|biomarker|clinical assessment|rating scale|scale\b", re.I)


def build_readiness(g, nodes):
    edges_by_node = defaultdict(list)
    for e in g["edges"]:
        edges_by_node[e["source"]].append(e)
        edges_by_node[e["target"]].append(e)
    diseases = sorted(n["id"] for n in nodes.values() if n["type"] == "disease")
    out = {}
    for did in diseases:
        gene = nodes[did].get("attrs", {}).get("gene") or did.split(":", 1)[1]
        gid = f"gene:{gene}"
        inc = edges_by_node[did]
        typ = lambda e, t: e["type"] == t
        other = lambda e: e["source"] if e["target"] == did else e["target"]

        def comp(status, edges, note, **extra):
            c = {"status": status, "edges": sorted({e["id"] for e in edges}), "note": note}
            c.update(extra)
            return c

        # assets covering the disease
        assets = [(e, nodes[e["source"]]) for e in inc if typ(e, "covers")]
        kind = lambda a: a["attrs"].get("kind")
        studies = [(e, nodes[e["source"]]) for e in inc if typ(e, "studies")]
        obs = [(e, s) for e, s in studies if s["attrs"].get("study_type") == "observational"]
        itv = [(e, s) for e, s in studies if s["attrs"].get("study_type") == "interventional"]

        # 1 registry / natural history
        reg = [(e, a) for e, a in assets if kind(a) in ("registry", "natural_history_study")]
        nh_obs = [(e, s) for e, s in obs if s["attrs"].get("atlas_role") in ("natural_history", "registry")
                  or re.search(r"natural history|registry", s["label"], re.I)]
        soft = [(e, a) for e, a in assets if kind(a) in ("data_platform", "biobank")]
        if reg or nh_obs:
            c1 = comp("yes", [e for e, _ in reg + nh_obs],
                      f"{len(reg)} registry/natural-history asset(s), {len(nh_obs)} observational natural-history/registry study record(s)")
        elif soft or obs:
            c1 = comp("partial", [e for e, _ in soft + obs],
                      f"no dedicated registry; {len(soft)} data platform/biobank, {len(obs)} other observational study(ies)")
        else:
            c1 = comp("no", [], "no registry, natural-history study or observational study in the graph")

        # 2 outcome measures / consortium
        om = [(e, a) for e, a in assets if kind(a) in ("outcome_measure", "trial_design")]
        net = [(e, a) for e, a in assets if kind(a) == "research_network"]
        om_obs = [(e, s) for e, s in obs if OUTCOME_WORDS.search(s["label"])]
        if om or net:
            c2 = comp("yes", [e for e, _ in om + net],
                      f"{len(om)} outcome-measure/trial-design asset(s), {len(net)} research network/consortium(s)")
        elif om_obs:
            c2 = comp("partial", [e for e, _ in om_obs],
                      "no consortium or outcome-measure asset; observational studies whose titles name outcome/biomarker work")
        else:
            c2 = comp("no", [], "no outcome-measure asset, consortium or outcome-focused study in the graph")

        # 3 animal or cell model
        am = [(e, a) for e, a in assets if kind(a) in ("animal_model", "cell_model")]
        scope_ids = {did, gid} | {e["source"] for e in edges_by_node[gid] if e["type"] == "variant_in"}
        model_edges, func_edges = [], []
        for nid in scope_ids:
            for e in edges_by_node[nid]:
                if e["type"] in ("shares_mechanism", "similar_phenotype", "candidate_for"):
                    continue  # disease-disease / hypothesis edges: the model may belong to the other disease
                st = {ev.get("study_type") for ev in e.get("evidence", []) if ev.get("supports", True)}
                if "animal_model" in st:
                    model_edges.append(e)
                elif "functional_study" in st:
                    func_edges.append(e)
        if am or model_edges:
            c3 = comp("yes", [e for e, _ in am] + model_edges,
                      f"{len(am)} model asset(s); {len(model_edges)} edge(s) on this disease/gene/variants cite animal-model evidence")
        elif func_edges:
            c3 = comp("partial", func_edges,
                      f"no animal model cited; {len(func_edges)} edge(s) cite functional (cell/in-vitro) studies")
        else:
            c3 = comp("no", [], "no model evidence on this disease, gene or its variant groups")

        # 4 interventional trial
        ranked = [(PHASE_RANK.get(s["attrs"].get("phase") or "", 0), e, s) for e, s in itv]
        if ranked:
            best = max(ranked, key=lambda t: (t[0], t[2]["attrs"].get("start") or ""))
            latest = max(ranked, key=lambda t: t[2]["attrs"].get("start") or "")
            active = [s for _, _, s in ranked if s["attrs"].get("status") in
                      ("RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING")]
            status = "yes" if best[0] >= 1 else "partial"
            c4 = comp(status, [e for _, e, _ in ranked],
                      f"{len(ranked)} interventional trial(s), {len(active)} active/recruiting",
                      highest_phase=best[2]["attrs"].get("phase"), highest_phase_trial=best[2]["id"],
                      latest_trial={"id": latest[2]["id"], "phase": latest[2]["attrs"].get("phase"),
                                    "start": latest[2]["attrs"].get("start"),
                                    "status": latest[2]["attrs"].get("status")})
        else:
            c4 = comp("no", [], "no interventional trial linked in the graph", highest_phase=None)

        # 5 approved therapy
        ther = [(e, nodes[e["source"]]) for e in inc if typ(e, "developed_for")]
        appr = [(e, t) for e, t in ther if t["attrs"].get("stage") == "approved"]
        if appr:
            c5 = comp("yes", [e for e, _ in appr], "approved: " + "; ".join(t["label"] for _, t in appr))
        elif nodes[did].get("attrs", {}).get("approved_treatment"):
            c5 = comp("partial", [], "disease attrs.approved_treatment is true but no approved therapy node is linked")
        else:
            clin = [(e, t) for e, t in ther if t["attrs"].get("stage") == "clinical"]
            c5 = comp("no", [e for e, _ in clin],
                      f"no approved therapy; {len(clin)} therapy(ies) at clinical stage" if clin else "no approved therapy in the graph")

        # 6 patient organisation
        orgs = [(e, nodes[e["source"]]) for e in inc if typ(e, "serves")]
        dedicated = [(e, o) for e, o in orgs if not UMBRELLA_SCOPE.search(o["attrs"].get("scope") or "")]
        if dedicated:
            c6 = comp("yes", [e for e, _ in orgs], f"{len(dedicated)} disease/gene-focused org(s), {len(orgs)} in total")
        elif orgs:
            c6 = comp("partial", [e for e, _ in orgs], f"only umbrella/multi-disease org(s) ({len(orgs)})")
        else:
            c6 = comp("no", [], "no patient organisation in the graph")

        # 7 known mechanism
        drv = [e for e in inc if typ(e, "driven_by")]
        strong = [e for e in drv if e.get("status") == "supported" and e.get("evidence_level") in
                  ("clinical", "curated", "experimental", "observational")]
        if strong:
            c7 = comp("yes", strong, f"{len(strong)} supported mechanism edge(s): " +
                      ", ".join(sorted({nodes[e['target']]['label'] for e in strong})))
        elif drv:
            c7 = comp("partial", drv, "mechanism edges are inferred, hypothesis-level or contested")
        else:
            c7 = comp("no", [], "no driven_by edge")

        # 8 research groups and grants
        res = [e for e in inc + edges_by_node[gid] if e["type"] == "works_on"]
        grants = [e for e in inc + edges_by_node[gid] if e["type"] == "about" and e["source"].startswith("grant:")]
        if res and grants:
            c8 = comp("yes", res + grants, f"{len({e['source'] for e in res})} researcher(s), {len({e['source'] for e in grants})} grant(s)")
        elif res or grants:
            c8 = comp("partial", res + grants, f"{len({e['source'] for e in res})} researcher(s), {len({e['source'] for e in grants})} grant(s)")
        else:
            c8 = comp("no", [], "no researcher or grant linked")

        comps = {"registry_or_natural_history": c1, "outcome_measures_or_consortium": c2,
                 "animal_or_cell_model": c3, "interventional_trial": c4, "approved_therapy": c5,
                 "patient_organisation": c6, "known_mechanism": c7, "research_groups_and_grants": c8}
        score = sum({"yes": 1, "partial": 0.5}.get(c["status"], 0) for c in comps.values())
        out[did] = {"label": nodes[did]["label"], "family": nodes[did].get("attrs", {}).get("family"),
                    "tally": score, "tally_of": 8,
                    "yes": [k for k, c in comps.items() if c["status"] == "yes"],
                    "components": comps}
    return {"meta": {"generated": TODAY, "source": "data/graph.json only",
                     "tally": "yes = 1, partial = 0.5, summed over 8 components. A descriptive count of what the "
                              "atlas has recorded, not a validated readiness score; 'no' means 'not in the graph'.",
                     "rules": {
                         "registry_or_natural_history": "yes: asset kind registry/natural_history_study covers it, or an observational study titled natural history/registry; partial: only a data platform/biobank or other observational study",
                         "outcome_measures_or_consortium": "yes: outcome_measure/trial_design/research_network asset; partial: observational study whose title names outcome/endpoint/biomarker",
                         "animal_or_cell_model": "yes: animal/cell model asset or an edge on the disease, gene or its variant groups citing animal_model evidence; partial: only functional_study evidence",
                         "interventional_trial": "yes: an interventional study with phase >= PHASE1; partial: only phase NA",
                         "approved_therapy": "yes: developed_for edge from a therapy with stage approved; partial: attrs.approved_treatment without a linked therapy",
                         "patient_organisation": "yes: a serving org whose scope is not umbrella/multi-gene; partial: umbrella orgs only",
                         "known_mechanism": "yes: a supported driven_by edge at curated/clinical/experimental/observational level; partial: only inferred/hypothesis/contested",
                         "research_groups_and_grants": "yes: both researcher works_on and grant about edges (disease or gene); partial: one of them"}},
            "diseases": out}


# --------------------------------------------------------------------------------------- channels

class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


REACH = [("research", re.compile(r"for[- ]researchers?|researcher[- ]resources|\bresearch\b", re.I)),
         ("registry", re.compile(r"registry|register|natural[- ]history", re.I)),
         ("participate", re.compile(r"participat|get[- ]involved|clinical[- ]trials?|studies|enrol", re.I)),
         ("contact", re.compile(r"contact", re.I))]


def dom(u):
    try:
        h = urllib.parse.urlparse(u).hostname or ""
    except ValueError:
        return ""
    return h.lower().removeprefix("www.")


def stored_pages():
    """domain -> list of (url, status, html_path)."""
    out = defaultdict(list)
    for d in WEB_DIRS:
        mf = d / "_manifest.json"
        if not mf.exists():
            continue
        for pid, m in json.load(open(mf)).items():
            h = d / f"{pid}.html"
            if not h.exists():
                continue
            url = m.get("final_url") or m.get("url")
            out[dom(url)].append((url, str(m.get("status")), h, d.relative_to(ROOT).as_posix() + f"/{pid}.html"))
    return out


_link_cache = {}


def reach_links(org_url, pages):
    """Research / registry / participate / contact pages an org's stored pages link to (same domain)."""
    d = dom(org_url)
    if not d or d not in pages:
        return []
    found = {}
    for url, status, path, rel in pages[d]:
        if status != "200":
            continue
        path_part = urllib.parse.urlparse(url).path
        for label, rx in REACH:
            if rx.search(path_part) and label not in found:
                found[label] = {"kind": label, "url": url, "seen_on": rel, "how": "stored page itself"}
        if path not in _link_cache:
            p = LinkParser()
            try:
                p.feed(path.read_text(errors="ignore"))
            except Exception:
                pass
            _link_cache[path] = p.links
        for href, text in _link_cache[path]:
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")) or "@" in href:
                continue
            full = urllib.parse.urljoin(url, href)
            if dom(full) != d:
                continue
            hay = f"{urllib.parse.urlparse(full).path} {text}"
            for label, rx in REACH:
                if label not in found and rx.search(hay) and len(text) < 60:
                    found[label] = {"kind": label, "url": full.split("#")[0], "link_text": text, "seen_on": rel,
                                    "how": "link on stored page"}
    return [found[k] for k, _ in REACH if k in found]


ORG_WORDS = re.compile(r"Univ|Hosp|H[oô]pita|Inc\b|Ltd|Institut|Cent(er|re)|Found|Fundaci|Pharma|Therap|Bio|Clinic|Klinik|"
                       r"Health|Corp|LLC|GmbH|S\.?A\b|S\.p\.A|B\.V|\bAG\b|Medic|College|Research|Network|NIH|National|"
                       r"Children|Assoc|Society|Group|Science|Co\.|Limited|Consortium|Gene|Searchlight|Herzzentrum|"
                       r"Assistance|Farmac|Laborator|Ministry|Agency|Trust|Council|Alliance|Fondazione|Fondation|Stiftung|"
                       r"Ospedal|Ziekenhuis|Azienda|Grupo|Cure\b|Company|Enterprises|\bAB\b|ApS|\bHF\b|\bSL\b|CHU\b|"
                       r"Ente\b|Helse|Region|County|Department|Academ|School|Program", re.I)
PERSON = re.compile(r"^[A-Z][\w'’-]+(?: (?:[a-z]{1,3} )*[A-Z][\w'’-]+){1,3}(?:,? (?:MD|M\.D\.|Dr|PhD|Prof)\.?)*$", re.U)


SPONSOR_CLASS = {}  # NCT -> ClinicalTrials.gov leadSponsor.class (INDUSTRY / OTHER / NIH / INDIVIDUAL ...)


def load_sponsor_classes(ncts):
    import gzip
    want = set(ncts)
    for f in sorted((ROOT / "data/raw/scale/ctgov").glob("studies_*.jsonl.gz")):
        with gzip.open(f, "rt") as fh:
            for line in fh:
                if '"nct"' not in line:
                    continue
                d = json.loads(line)
                if d.get("nct") in want and isinstance(d.get("lead"), dict):
                    SPONSOR_CLASS[d["nct"]] = d["lead"].get("class")
    for f in ROOT.glob("data/raw/**/clinicaltrials/NCT*.json"):
        if f.stem in want and f.stem not in SPONSOR_CLASS:
            try:
                m = re.search(r'"leadSponsor":\s*\{[^}]*"class":\s*"(\w+)"', f.read_text())
            except OSError:
                m = None
            if m:
                SPONSOR_CLASS[f.stem] = m.group(1)


def sponsor_text(sp, nct=None):
    """Sponsor at organisation level; individual-investigator sponsors are not named.
    Uses ClinicalTrials.gov's sponsor class when cached; otherwise a name heuristic."""
    sp = (sp or "").strip().rstrip(".")
    if not sp:
        return "Sponsor not listed"
    cls = SPONSOR_CLASS.get(nct)
    # CT.gov often files sponsor-investigators under OTHER/OTHER_GOV, so the name heuristic also runs for OTHER/unknown.
    individual = cls == "INDIVIDUAL" or (cls not in ("INDUSTRY", "NIH", "FED") and bool(PERSON.match(sp)) and not ORG_WORDS.search(sp))
    if individual:
        return "Investigator-sponsored study (sponsor is an individual; use the record's site/institution contacts)"
    return f"Sponsor: {sp}"


def sponsor_field(sp, nct=None):
    t = sponsor_text(sp, nct)
    return t[len("Sponsor: "):] if t.startswith("Sponsor: ") else None


ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}
ASSET_CHANNEL = {"registry": "registry", "natural_history_study": "natural_history_study",
                 "data_platform": "data_platform", "biobank": "biobank", "research_network": "research_network",
                 "outcome_measure": "consortium"}


def build_channels(g, nodes, deep):
    pages = stored_pages()
    channels = {}
    load_sponsor_classes([n[6:] for n in nodes if n.startswith("study:")] +
                         list(json.load(open(SCALE / "trials.json"))["studies"]))

    def add(cid, base, disease, ev):
        c = channels.setdefault(cid, dict(base, diseases=[], evidence=[]))
        if disease not in c["diseases"]:
            c["diseases"].append(disease)
        if ev not in c["evidence"]:
            c["evidence"].append(ev)

    maint = defaultdict(list)
    for e in g["edges"]:
        if e["type"] == "maintains" and nodes[e["source"]]["type"] == "patient_org":
            maint[e["target"]].append(nodes[e["source"]]["label"])

    for e in g["edges"]:
        if e["target"] not in deep:
            continue
        s = nodes[e["source"]]
        ev = {"edge": e["id"]}
        if e["type"] == "covers" and s["attrs"].get("kind") in ASSET_CHANNEL:
            a = s["attrs"]
            how = a.get("access") or "See the asset page."
            if maint[s["id"]]:
                how += f" (run with {', '.join(maint[s['id']])})"
            add(s["id"], {"id": s["id"], "type": ASSET_CHANNEL[a["kind"]], "name": s["label"], "url": a.get("url"),
                          "how_to_reach": how, "layer": "deep"}, e["target"], ev)
        elif e["type"] == "serves":
            a = s["attrs"]
            links = reach_links(a.get("url"), pages)
            how = ("; ".join(f"{l['kind']} page: {l['url']}" for l in links)
                   if links else "Organisation website (no research/contact page found on its stored pages).")
            add(s["id"], {"id": s["id"], "type": "patient_org", "name": s["label"], "url": a.get("url"),
                          "country": a.get("country"), "scope": a.get("scope"), "how_to_reach": how,
                          "reach_links": links, "layer": "deep"}, e["target"], ev)
        elif e["type"] == "studies" and s["attrs"].get("status") in ACTIVE:
            a = s["attrs"]
            add(s["id"], {"id": s["id"], "type": "recruiting_trial", "name": s["label"], "url": a.get("url"),
                          "status": a.get("status"), "phase": a.get("phase"), "study_type": a.get("study_type"),
                          "sponsor": sponsor_field(a.get("sponsor"), s["id"][6:]),
                          "how_to_reach": f"{sponsor_text(a.get('sponsor'), s['id'][6:])}. Use the 'Contacts and Locations' section of the "
                                          "ClinicalTrials.gov record (central/site contacts are not copied here).",
                          "layer": "deep"}, e["target"], ev)

    # ---- breadth layer
    ids_to_deep = defaultdict(set)
    gene_to_deep = defaultdict(set)
    for did, d in deep.items():
        for o in d["omim"]:
            ids_to_deep[f"OMIM:{o}"].add(did)
        for o in d["orpha"]:
            ids_to_deep[f"ORPHA:{o}"].add(did)
        for m in d["mondo"]:
            ids_to_deep[m].add(did)
        gene_to_deep[d["gene"]].add(did)

    orgs = json.load(open(SCALE / "orgs.json"))
    for o in orgs["orgs"]:
        for dd in o.get("diseases", []):
            hits = ids_to_deep.get(dd["id"], set()) | ids_to_deep.get(dd.get("mondo") or "", set())
            for did in hits:
                ev = {"scale": "data/derived/scale/orgs.json", "org": o["id"], "disease_id": dd["id"],
                      "rule": dd.get("evidence", {}).get("rule"), "source": dd.get("evidence", {}).get("source"),
                      "url": dd.get("evidence", {}).get("url"), "quote": dd.get("evidence", {}).get("quote")}
                if o["id"] in channels:
                    add(o["id"], {}, did, ev)
                    continue
                site = o.get("website") or o.get("url")
                links = reach_links(site, pages) if o.get("website") else []
                how = ("; ".join(f"{l['kind']} page: {l['url']}" for l in links) if links else
                       ("Organisation website" if o.get("website") else "Directory profile") +
                       (f"; directory profile: {o['directory_profile']}" if o.get("directory_profile") and o.get("website") else ""))
                add(o["id"], {"id": o["id"], "type": "patient_org", "name": o["name"], "url": site,
                              "country": o.get("country"), "how_to_reach": how, "reach_links": links,
                              "layer": "scale (automated match)"}, did, ev)

    assets = json.load(open(SCALE / "assets.json"))
    for a in assets["assets"]:
        for dd in a.get("diseases", []):
            ids = dd.get("ids") or [dd.get("id")]
            hits = set().union(*[ids_to_deep.get(i, set()) for i in ids if i])
            if dd.get("gene"):
                hits |= gene_to_deep.get(dd["gene"], set())
            for did in hits:
                ev = {"scale": "data/derived/scale/assets.json", "asset": a["id"], "disease_ids": ids,
                      "rule": dd.get("evidence", {}).get("rule"), "url": dd.get("evidence", {}).get("url"),
                      "quote": dd.get("evidence", {}).get("quote")}
                if a["id"] in channels:
                    add(a["id"], {}, did, ev)
                    continue
                gn = nodes.get(a["id"])
                if gn and gn["attrs"].get("access"):
                    how = gn["attrs"]["access"]
                elif a.get("program"):
                    how = f"Registry listed on {a['program']} ({a.get('listed_at')}); researcher access via the registry site."
                else:
                    how = "Multi-disease registry/platform; see its site for participation and researcher access."
                add(a["id"], {"id": a["id"], "type": ASSET_CHANNEL.get(a.get("kind"), a.get("kind")), "name": a["name"],
                              "url": a.get("url"), "how_to_reach": how, "layer": "scale (automated match)"}, did, ev)

    trials = json.load(open(SCALE / "trials.json"))
    st = trials["studies"]
    for did, d in deep.items():
        tops = []
        for i in d["omim"]:
            tops += trials["diseases"].get(f"OMIM:{i}", {}).get("top", [])
        for i in d["orpha"]:
            tops += trials["diseases"].get(f"ORPHA:{i}", {}).get("top", [])
        tops += trials["genes"].get(d["gene"], {}).get("top", [])
        for t in tops:
            s = st.get(t["nct"])
            if not s or s.get("status") not in ACTIVE:
                continue
            cid = f"study:{t['nct']}"
            ev = {"scale": "data/derived/scale/trials.json", "nct": t["nct"], "rule": t.get("rule"), "quote": t.get("quote")}
            if cid in channels:
                add(cid, {}, did, ev)
                continue
            add(cid, {"id": cid, "type": "recruiting_trial", "name": s["title"], "url": s["url"], "status": s["status"],
                      "phase": "/".join(s.get("phases") or []) or None, "study_type": (s.get("type") or "").lower(),
                      "sponsor": sponsor_field(s.get("sponsor"), t["nct"]),
                      "how_to_reach": f"{sponsor_text(s.get('sponsor'), t['nct'])}. Use the 'Contacts and Locations' section of the "
                                      "ClinicalTrials.gov record (central/site contacts are not copied here).",
                      "layer": "scale (automated match)"}, did, ev)

    # by-disease index
    by_d = {did: defaultdict(list) for did in deep}
    for c in channels.values():
        for did in c["diseases"]:
            by_d[did][c["type"]].append(c["id"])
    items = sorted(channels.values(), key=lambda c: (c["type"], c["name"] or ""))
    for c in items:
        c["diseases"].sort()
        c.setdefault("reach_links", None)
        if c["reach_links"] is None:
            del c["reach_links"]
    counts = defaultdict(int)
    for c in items:
        counts[c["type"]] += 1
    return {"meta": {"generated": TODAY,
                     "sources": ["data/graph.json", "data/derived/scale/orgs.json", "data/derived/scale/assets.json",
                                 "data/derived/scale/trials.json", "stored org pages under data/raw/**/web/"],
                     "policy": "Organisational channels only. No personal names, e-mail addresses or phone numbers; "
                               "mailto:/tel: links are skipped. Trials are given at sponsor level with the registry record.",
                     "evidence": "Deep-layer items cite graph edge ids ({edge}); breadth-layer items cite the scale file, "
                                 "matching rule and verbatim quote ({scale, rule, quote}). Breadth matches are automated.",
                     "active_trial_statuses": sorted(ACTIVE),
                     "counts": dict(counts, total=len(items),
                                    diseases_with_channel=sum(1 for v in by_d.values() if v))},
            "channels": items,
            "by_disease": {k: dict(v) for k, v in sorted(by_d.items())}}


# --------------------------------------------------------------------------------------- main

def dump(name, obj):
    p = OUT / name
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    return p


def main():
    if "--fetch" in sys.argv or not PREV_XML.exists():
        fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    g, nodes = load_graph()
    index_rows = json.load(open(INDEX))["rows"]
    deep = deep_ids(nodes, index_rows)
    prev = build_prevalence(index_rows, deep)
    ready = build_readiness(g, nodes)
    # attach headline population to readiness for convenience
    for did, r in ready["diseases"].items():
        ep = prev["deep"][did]["estimated_people"]
        r["estimated_people_worldwide"] = ep.get("worldwide", {}).get("text") if ep else None
    chans = build_channels(g, nodes, deep)
    orpha_all = {"meta": {"generated": TODAY, "source": prev["meta"]["source"], "method": METHOD},
                 "orpha": prev.pop("orpha")}
    for name, obj in (("prevalence.json", prev), ("prevalence_orpha.json", orpha_all), ("readiness.json", ready), ("channels.json", chans)):
        p = dump(name, obj)
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size/1e6:.2f} MB")
    print(json.dumps(prev["meta"]["counts"]))
    print(json.dumps(chans["meta"]["counts"]))


if __name__ == "__main__":
    main()
