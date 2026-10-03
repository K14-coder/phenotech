import json, sys
from collections import Counter
f=json.load(open('/Users/khezanirani/Desktop/hacknation/data/curated/biology.json'))
ids={n['id'] for n in f['nodes']}
PRE={"gene":"gene","disease":"disease","vg":"variant_group","mech":"mechanism","phenotype":"phenotype","therapy":"therapy"}
RT={("gene","disease"):{"causes"},("variant_group","gene"):{"variant_in"},("variant_group","mechanism"):{"has_effect"},
    ("gene","mechanism"):{"participates_in"},("disease","mechanism"):{"driven_by"},("disease","phenotype"):{"has_phenotype"},
    ("disease","disease"):{"shares_mechanism","similar_phenotype"},("therapy","mechanism"):{"targets"},("therapy","disease"):{"developed_for"}}
EV_SRC={"HGNC","MONDO","OMIM","Orphanet","HPO","ClinVar","ClinGen","GO","UniProt","PubMed","ClinicalTrials.gov","NIH RePORTER","OpenTargets","Monarch","Website","Atlas","Expert"}
EV_KIND={"database","publication","trial","grant","website","computed","expert"}
LVL={"clinical","curated","experimental","observational","inferred","hypothesis"}; STAT={"supported","contested","unverified"}
errs=[]; seen=set()
for n in f['nodes']:
    a=n.get('attrs') or {}
    if n['type']=='variant_group' and a.get('consequence') not in {"truncating","missense","splice","cnv","mixed"}: errs.append(f"{n['id']} consequence")
    if n['type']=='mechanism' and a.get('kind') not in {"effect","process"}: errs.append(f"{n['id']} mech kind")
    if n['type']=='therapy' and a.get('stage') not in {"idea","preclinical","clinical","approved"}: errs.append(f"{n['id']} stage")
    if n['type']=='phenotype' and not isinstance(a.get('ic'),(int,float)): errs.append(f"{n['id']} ic")
for e in f['edges']:
    if e['id'] in seen: errs.append(f"dup {e['id']}")
    seen.add(e['id'])
    if e['id']!=f"{e['source']}|{e['type']}|{e['target']}": errs.append(f"id mismatch {e['id']}")
    for k in ('source','target'):
        if e[k] not in ids: errs.append(f"{e['id']} dangling {k}")
    st,tt=PRE[e['source'].split(':')[0]], PRE[e['target'].split(':')[0]]
    if e['type'] not in RT.get((st,tt),set()): errs.append(f"{e['id']} illegal {st}->{tt}")
    if e['evidence_level'] not in LVL or e['status'] not in STAT or not (0<=e['confidence']<=1): errs.append(f"{e['id']} enum/conf")
    if e['evidence_level']!='hypothesis' and not e.get('evidence'): errs.append(f"{e['id']} NO EVIDENCE")
    if not e.get('explanation'): errs.append(f"{e['id']} no explanation")
    for ev in e.get('evidence',[])+e.get('counter_evidence',[]):
        for k in ('source','ref','url','kind','extracted_by','retrieved'):
            if not ev.get(k): errs.append(f"{e['id']} ev missing {k}")
        if ev['source'] not in EV_SRC: errs.append(f"{e['id']} ev source {ev['source']}")
        if ev['kind'] not in EV_KIND: errs.append(f"{e['id']} ev kind {ev['kind']}")
        if ev['extracted_by'] not in {"database","agent-curation","computed"}: errs.append(f"{e['id']} extracted_by")
        if ev['source']=='PubMed' and not ev.get('quote'): errs.append(f"{e['id']} PubMed no quote")
        if ev.get('quote') and ev.get('verified') is not True: errs.append(f"{e['id']} UNVERIFIED {ev['ref']}")
for c in f['clusters']:
    if c['basis'] not in {"mechanism","phenotype","pathway"}: errs.append(f"{c['id']} basis")
    errs += [f"{c['id']} unknown member {m}" for m in c['members'] if m not in ids]
    errs += [f"{c['id']} unknown edge {x}" for x in c['edge_ids'] if x not in seen]
    if not c['edge_ids']: errs.append(f"{c['id']} no edge_ids")
for g in f['gaps']:
    for k in ('id','about','question','what_is_missing','searched','how_to_find_out'):
        if not g.get(k): errs.append(f"{g['id']} missing {k}")
print("SCHEMA ERRORS:", len(errs))
for x in errs[:25]: print("  -", x)
print("status:", dict(Counter(e['status'] for e in f['edges'])))
print("levels:", dict(Counter(e['evidence_level'] for e in f['edges'])))
print("w/ counter_evidence:", sum(1 for e in f['edges'] if e.get('counter_evidence')), "| contradicting items:", sum(1 for e in f['edges'] for x in e.get('evidence',[])+e.get('counter_evidence',[]) if x.get('supports') is False))
print("unique PMIDs cited:", len({x['ref'] for e in f['edges'] for x in e.get('evidence',[])+e.get('counter_evidence',[]) if x['ref'].startswith('PMID')}))
print("KB:", round(len(open('/Users/khezanirani/Desktop/hacknation/data/curated/biology.json','rb').read())/1024))
