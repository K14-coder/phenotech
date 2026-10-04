"""Cross-family mechanism curation -> data/curated/cross_family.json (SCHEMA fragment).

Every claim below is a gene/variant-group -> mechanism edge between EXISTING atlas nodes (plus one new
GO-backed mechanism node, mech:autophagy). Each PubMed quote is re-checked as a normalised substring
of the stored abstract in data/raw/families/cross/pubmed/<PMID>.json; GO evidence is taken from the
stored QuickGO annotation searches in data/raw/families/cross/quickgo/. The build FAILS (exit 1) on
any unverified quote, missing endpoint or missing source file. Nothing is written in that case.

Run:  python3 pipeline/families/cross/fetch.py <PMIDs...>   (once, to store the abstracts)
      python3 pipeline/families/cross/quickgo.py           (once, GO annotation matrix)
      python3 pipeline/families/cross/build.py
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "families" / "cross"
OUT = ROOT / "data" / "curated" / "cross_family.json"
TODAY = datetime.date.today().isoformat()


def norm(s: str) -> str:  # same normalisation as pipeline/families/rasopathy/ras_common.py
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
         .replace(" ", " ").replace("​", ""))
    return " ".join(s.split())


# (pmid, quote, study_type, supports)
P = lambda pmid, quote, st="functional_study": (pmid, quote, st)  # noqa: E731

CLAIMS = [
    # ---------------- 1. RAS -> MAPK cascade (closes gap:ras-to-mapk-hierarchy at gene level) ----------
    dict(src="gene:LZTR1", type="participates_in", tgt="mech:mapk-cascade", level="experimental", conf=0.85,
         expl="LZTR1 is the adaptor that tags RAS proteins for ubiquitin-mediated degradation; losing it, or carrying "
              "dominant Noonan-syndrome LZTR1 mutations, increases the RAS pool and RAS-MAPK (ERK) pathway activity.",
         pubs=[P("30442766", "We propose that LZTR1 acts as a conserved regulator of RAS ubiquitination and MAPK pathway activation."),
               P("30481304", "We provide the first evidence that these mutations, but not the missense changes occurring as biallelic mutations in recessive NS, enhance stimulus-dependent RAS-MAPK signaling, which is triggered, at least in part, by an increased RAS protein pool."),
               P("31337872", "Here, we demonstrate that LZTR1 facilitates the polyubiquitination and degradation of RAS via the ubiquitin-proteasome pathway, leading to the inhibition of the RAS/MAPK signaling.")]),
    dict(src="gene:RIT1", type="participates_in", tgt="mech:mapk-cascade", level="experimental", conf=0.85,
         expl="Noonan-syndrome RIT1 variants increase MEK-ERK signalling and ERK-target (ELK1) transactivation in cell "
              "assays; pathogenic RIT1 or LZTR1 mutations prevent normal LZTR1-mediated RIT1 degradation.",
         pubs=[P("25959749", "Both variants resulted in increased MEK-ERK signaling compared to wild-type, underscoring gain-of-function as the primary functional mechanism."),
               P("23791108", "Luciferase assays in NIH 3T3 cells showed that five RIT1 alterations identified in children with Noonan syndrome enhanced ELK1 transactivation."),
               P("30872527", "Pathogenic mutations affecting either RIT1 or LZTR1 resulted in incomplete degradation of RIT1. This led to RIT1 accumulation and dysregulated growth factor signaling responses.", "animal_model")]),
    dict(src="gene:RIT1", type="participates_in", tgt="mech:ras-protein-signal-transduction", level="curated", conf=0.9,
         expl="RIT1 encodes a RAS-subfamily GTPase; Gene Ontology annotates it to Ras protein signal transduction "
              "(GO:0007265, IDA from the paper that linked RIT1 to Noonan syndrome).",
         go=("Q92963", "GO:0007265", "RIT1"),
         pubs=[P("23791108", "we identified a total of nine missense, nonsynonymous mutations in RIT1, encoding a member of the RAS subfamily")]),
    dict(src="gene:SOS1", type="participates_in", tgt="mech:mapk-cascade", level="experimental", conf=0.85,
         expl="SOS1 is a RAS guanine-nucleotide exchange factor; Noonan-syndrome SOS1 mutants enhance RAS and ERK "
              "activation in two independent studies.",
         pubs=[P("17143285", "Noonan syndrome-associated SOS1 mutations are hypermorphs encoding products that enhance RAS and ERK activation."),
               P("17143282", "In addition, ectopic expression of two Noonan syndrome-associated mutants induces enhanced RAS and ERK activation.")]),
    dict(src="gene:CBL", type="participates_in", tgt="mech:mapk-cascade", level="experimental", conf=0.8,
         expl="Germline CBL mutants found in a Noonan-like disorder cause constitutive or enhanced ERK phosphorylation "
              "in cell models, which the authors attribute to augmented RAS-MAPK signalling.",
         pubs=[P("20694012", "the common p.371Y>H altered Cbl protein induces cytokine-independent growth and constitutive phosphorylation of ERK, AKT and S6 only in hematopoietic cells in which normal Cbl expression is reduced by RNA interference"),
               P("25178484", "Since we detected enhanced ERK phosphorylation in cells expressing mutant CBL, we conclude that aberrant EGFR trafficking contributes to augmented RAS-MAPK signaling, the common trait of Noonan syndrome and related RASopathies.")]),
    # ---------------- 2. SYNGAP1 (DEE) <-> RASopathy bridge -----------------------------------------
    dict(src="gene:SYNGAP1", type="participates_in", tgt="mech:mapk-cascade", level="experimental", conf=0.85,
         expl="SynGAP is a synaptic Ras GTPase-activating protein. Heterozygous or knockout Syngap1 mice and neurons "
              "show raised ERK activation and MEK/ERK hyperphosphorylation, the same pathway over-activated in RASopathies. "
              "The same papers note limits: SynGAP's role in LTP likely involves other targets, and a MEK inhibitor "
              "normalised basal transmission but not the LTP deficit in Syngap1+/- mice (PMID 12427827, 29940508).",
         pubs=[P("12427827", "Although basal levels of activated ERK2 were elevated in hippocampal extracts from SynGAP(-/+) mice, NMDAR stimulation still induced a robust increase in ERK activation in slices from SynGAP(-/+) mice.", "animal_model"),
               P("16537406", "Furthermore, ERK activation is up-regulated in neurons from SynGAP knockout mice, whereas P38 MAPK function is depressed."),
               P("29940508", "SYNGAP1 deficiency is associated with hyperphosphorylation of MEK and ERK kinases and with altered synaptic function in Syngap1+/- mice.", "animal_model")]),
    # ---------------- 3. mTOR signalling: RAS (NF1) + DEE (SYNGAP1, CDKL5) + lysosomal ---------------
    dict(src="gene:SYNGAP1", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.6,
         expl="In cortical neurons SynGAP limits protein synthesis through a pathway that involves ERK, mTOR and Rheb.",
         pubs=[P("24391850", "The data presented here from in vitro, rat and mouse cortical networks, demonstrate that regulation of translation by SynGAP involves ERK, mTOR, and the small GTP-binding protein Rheb.")]),
    dict(src="gene:NF1", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.65,
         expl="Neurofibromin (a RasGAP) restrains mTOR: mTOR is constitutively active in NF1-deficient cells and tumours, "
              "through Ras, PI3K and AKT inactivation of TSC2.",
         pubs=[P("15937108", "We show here that the mTOR pathway is tightly regulated by neurofibromin. mTOR is constitutively activated in both NF1-deficient primary cells and human tumors in the absence of growth factors.")]),
    dict(src="gene:CDKL5", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.75,
         expl="Two independent CDKL5 mouse models show altered AKT-mTOR signalling after CDKL5 loss.",
         pubs=[P("30288694", "Taken together, these data support a model in which loss of CDKL5 alters mTOR signaling and synaptic compositions in a neuron-type specific manner", "animal_model"),
               P("23236174", "kinome profiling uncovers disruption of multiple signal transduction pathways, including the AKT-mammalian target of rapamycin (mTOR) cascade, upon Cdkl5 loss-of-function", "animal_model")]),
    dict(src="gene:NPC1", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.8,
         expl="Loss of the lysosomal cholesterol exporter NPC1 traps cholesterol in lysosomes and drives mTORC1 "
              "hyperactivation; mTORC1 inhibition restores lysosomal proteolysis in NPC models.",
         pubs=[P("33308480", "In Niemann-Pick type C (NPC), loss of the cholesterol exporter, NPC1, causes cholesterol accumulation within lysosomes, leading to mTORC1 hyperactivation, disrupted mitochondrial function, and neurodegeneration."),
               P("31548609", "OSBP-mediated cholesterol trafficking drives constitutive mTORC1 activation in a disease model caused by the loss of the lysosomal cholesterol transporter, Niemann-Pick C1 (NPC1).")]),
    dict(src="gene:GBA1", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.6,
         expl="In Gaucher-disease iPSC neurons mTORC1 is hyperactive, driven by glycosphingolipid accumulation, and "
              "mTOR inhibition restores lysosomal biogenesis and autophagic clearance.",
         pubs=[P("31519738", "We found that mTORC1 is hyperactive in GD cells as evidenced by increased phosphorylation of its downstream protein substrates.")]),
    dict(src="gene:GAA", type="participates_in", tgt="mech:tor-signaling", level="experimental", conf=0.6,
         expl="mTOR signalling is dysregulated in Pompe-disease muscle cells; reactivating mTOR in Pompe mice reversed "
              "atrophy and autophagic buildup.",
         pubs=[P("28130275", "Here, we report the dysregulation of mTOR signaling in the diseased muscle cells, and we focus on potential sites for therapeutic intervention.", "animal_model")]),
    # ---------------- 4. Synaptic plasticity: RASopathy + lysosomal join DEE/SNARE --------------------
    dict(src="gene:PTPN11", type="participates_in", tgt="mech:regulation-of-synaptic-plasticity", level="experimental", conf=0.8,
         expl="Noonan-syndrome Ptpn11 (SHP2) mutations raise ERK activity in excitatory hippocampal neurons and impair "
              "long-term potentiation and spatial learning in mice; MEK inhibition or lovastatin reversed the deficits.",
         pubs=[P("25383899", "Our results demonstrate that increased basal Erk activity and corresponding baseline increases in excitatory synaptic function are responsible for the LTP impairments and, consequently, the learning deficits in mouse models of NS.", "animal_model"),
               P("30837304", "expressing the NS-associated mutant SHP2D61G in excitatory, but not inhibitory, hippocampal neurons increased ERK signaling and impaired both long-term potentiation (LTP) and spatial memory in mice", "animal_model")]),
    dict(src="gene:NF1", type="participates_in", tgt="mech:regulation-of-synaptic-plasticity", level="experimental", conf=0.6,
         expl="In Nf1 mutant mice, neurofibromin-regulated ERK/synapsin I signalling increases GABA release, which "
              "modulates hippocampal LTP and learning.",
         pubs=[P("18984165", "Our results demonstrate that neurofibromin modulates ERK/synapsin I-dependent GABA release, which in turn modulates hippocampal LTP and learning.", "animal_model")]),
    dict(src="gene:HRAS", type="participates_in", tgt="mech:regulation-of-synaptic-plasticity", level="experimental", conf=0.75,
         expl="Activated H-Ras (G12V) changes synaptic plasticity in mice: it enhances presynaptic plasticity in visual "
              "cortex, and Costello-syndrome HRas G12V mice have impaired mGluR-dependent LTD (LTP was unaffected).",
         pubs=[P("20937865", "We show that a constitutively active form of H-ras (H-ras(G12V)), expressed presynaptically at excitatory synapses in mice, accelerates and enhances multiple, mechanistically distinct forms of plasticity in the developing visual cortex.", "animal_model"),
               P("28455524", "HRas G12V/G12V mice showed robust upregulation of ERK signaling, neuronal hypertrophy, increased brain volume, spatial learning deficits, and impaired mGluR-dependent long-term depression (LTD).", "animal_model")]),
    dict(src="gene:GBA1", type="participates_in", tgt="mech:regulation-of-synaptic-plasticity", level="experimental", conf=0.5,
         expl="In heterozygous Gba1 L444P mice (a Parkinson-risk model, not Gaucher disease itself) hippocampal synaptic "
              "plasticity and basal transmission are disrupted, independently of substrate accumulation.",
         pubs=[P("39562000", "The mutation disrupts hippocampal synaptic plasticity and basal synaptic transmission by reducing the density of hippocampal CA3-CA1 synapses", "animal_model")]),
    # ---------------- 5. Neurotransmitter release: CACNA1A (DEE) <-> SNARE ----------------------------
    dict(src="gene:CACNA1A", type="participates_in", tgt="mech:ca-triggered-exocytosis", level="experimental", conf=0.75,
         expl="CaV2.1 (P/Q-type) channels supply the presynaptic Ca2+ that triggers neurotransmitter release; gain-of-function "
              "(S218L) knock-in mice release more transmitter and loss-of-function (leaner) mice release less.",
         pubs=[P("20631222", "These channels mediate neurotransmitter release at many central synapses and at the neuromuscular junction (NMJ).", "animal_model"),
               P("18293354", "Ln/wt mice had approximately 25% reduced spontaneous uniquantal ACh release and approximately 10% reduced nerve-stimulation evoked release, compared with wild-type.", "animal_model")]),
    # ---------------- 6. Protein misfolding: DEE channels join the lysosomal/SNARE chaperone bridge ----
    dict(src="vg:SCN1A:missense", type="has_effect", tgt="mech:protein-destabilization", level="experimental", conf=0.75,
         expl="Several epileptogenic SCN1A (NaV1.1) missense mutants are folding-defective, reach the cell surface poorly, "
              "and can be partly rescued by low temperature, interacting proteins or pharmacological chaperones. This "
              "applies to a subset of missense variants, not all.",
         pubs=[P("19402159", "Thus, loss of function caused by folding defects that can be attenuated by molecular interactions may be a common pathogenic mechanism for Na(v)1.1 epileptogenic mutants."),
               P("25576396", "Thus, Na(V)1.1 folding defective mutants can be relatively common and mutations inducing rescuable folding defects are spread in all Na(V)1.1 domains.")]),
    dict(src="vg:KCNQ2:missense-lof", type="has_effect", tgt="mech:protein-destabilization", level="experimental", conf=0.55,
         expl="An epilepsy KCNQ2 (Kv7.2) missense variant, W344R, misfolds during translation, giving non-functional "
              "channels that fail to traffic; misfolding has been suggested for other KCNQ2 epilepsy variants.",
         pubs=[P("34020651", "Mutations in the KCNQ2 gene associated with human epilepsy have been suggested to cause misfolding of the encoded Kv7.2 channel."),
               P("34020651", "this mutation impedes proper folding during translation within the cell by forcing the nascent chain to follow a folding route that leads to a non-native configuration")]),
    # ---------------- 7. Autophagy (new GO node): lysosomal + CDKL5 ----------------------------------
    dict(src="gene:CDKL5", type="participates_in", tgt="mech:autophagy", level="experimental", conf=0.7,
         expl="CDKL5 kinase activity drives selective autophagy of protein aggregates (via SINTBAD/TBK1/p62) and of viral "
              "capsids; CDKL5-deficient mice accumulate insoluble protein aggregates in the brain.",
         pubs=[P("42779792", "These findings define a CDKL5/SINTBAD/TBK1 signaling axis that couples proteotoxic stress to activation of selective autophagy receptors and identify impaired proteostasis as a previously unrecognized consequence of CDKL5 deficiency."),
               P("37917202", "We found that deletion of CDKL5 or expression of a clinically relevant pathogenic mutant of CDKL5 reduced virophagy of Sindbis virus (SINV)")]),
    dict(src="gene:GBA1", type="participates_in", tgt="mech:autophagy", level="curated", conf=0.9,
         expl="Gene Ontology annotates GBA1 to autophagy (IMP), and autophagy-lysosomal dysfunction is described as a key "
              "event in GBA1-associated neurodegeneration.",
         go=("P04062", "GO:0006914", "GBA1"),
         pubs=[P("31519738", "Dysfunction of the autophagy-lysosomal pathway represents a key pathogenic event in GBA1-associated neurodegeneration.")]),
    dict(src="gene:NPC1", type="participates_in", tgt="mech:autophagy", level="curated", conf=0.9,
         expl="Gene Ontology annotates NPC1 to autophagy (IGI); in NPC cell models, suppressing aberrant mTORC1 signalling "
              "restores autophagic function.",
         go=("O15118", "GO:0006914", "NPC1"),
         pubs=[P("31548609", "Chemical and genetic inactivation of OSBP suppresses aberrant mTORC1 signalling and restores autophagic function in cellular models of Niemann-Pick type C (NPC).")]),
    dict(src="gene:GAA", type="participates_in", tgt="mech:autophagy", level="curated", conf=0.9,
         expl="Gene Ontology annotates GAA to glycophagy, a form of autophagy (IMP); Pompe mouse muscle shows autophagic "
              "buildup that mTOR reactivation removed.",
         go=("P10253", "GO:0006914", "GAA"),
         pubs=[P("28130275", "Reactivation of mTOR in the whole muscle of Pompe mice by TSC knockdown resulted in the reversal of atrophy and a striking removal of autophagic buildup.", "animal_model")]),
    dict(src="gene:CLN3", type="participates_in", tgt="mech:autophagy", level="curated", conf=0.8,
         expl="Gene Ontology annotates CLN3 to autophagy-related terms (ISS/IEA); CLN3-knockout cells show altered "
              "autophagy-lysosome function (more autophagosomes, fewer lysosomes, lower lysosomal enzyme activity).",
         go=("Q13286", "GO:0006914", "CLN3"),
         pubs=[P("34964690", "We observed in PSENEN- and CLN3-knockout cells corresponding alterations in the autophagy-lysosome system.")]),
]

NEW_NODES = [{
    "id": "mech:autophagy", "type": "mechanism", "label": "Autophagy", "xrefs": {"GO": "GO:0006914"},
    "summary": "The cell's self-digestion pathway: material is wrapped in autophagosomes and delivered to lysosomes for breakdown.",
    "attrs": {"kind": "process", "go_id": "GO:0006914", "go_name": "autophagy", "family": "cross"},
    "sources": [{"source": "GO", "ref": "GO:0006914", "url": "https://www.ebi.ac.uk/QuickGO/term/GO:0006914",
                 "title": "autophagy (GO:0006914), go-basic.obo", "kind": "database", "study_type": "database_record",
                 "extracted_by": "database", "retrieved": TODAY}],
}]

GAPS = [
    {"id": "gap:cross-rasopathy-calcium-excitability", "about": "RASopathies / mech:voltage-gated-calcium-channel-activity",
     "question": "Do RASopathy genes change neuronal calcium-channel function or excitability in a way that maps onto the DEE channel mechanisms?",
     "what_is_missing": ["Found: NF1 loss reduces HCN channel current and raises interneuron excitability (PMID:25917366, PMID:35589737); "
                         "Noonan SHP2 mutants enhance Ca2+ oscillations in cardiomyocytes (PMID:16461457). Neither maps onto an existing "
                         "atlas mechanism node (no HCN or calcium-signalling node), so no edge was added."],
     "searched": ["PubMed: (Nf1 OR neurofibromin) AND (HCN OR sodium channel OR calcium channel) AND neurons",
                  "PubMed: (Noonan OR RASopathy) AND calcium AND (cardiomyocyte* OR channel)"],
     "how_to_find_out": "Add a GO-backed node such as 'regulation of neuronal action potential' only if a DEE gene can be attached with the same evidence standard."},
    {"id": "gap:cross-er-stress", "about": "mech:protein-destabilization",
     "question": "Is ER stress / the unfolded protein response a shared process across lysosomal, SNARE and DEE genes?",
     "what_is_missing": ["QuickGO: none of the 45 deep-disease genes is annotated to 'response to endoplasmic reticulum stress' (GO:0034976) or descendants.",
                         "Misfolding is now sourced for SCN1A and KCNQ2 missense subsets, but no abstract checked shows UPR activation in DEE or SNARE patient cells."],
     "searched": ["QuickGO annotation search GO:0034976 for all 45 genes", "PubMed: SCN1A / KCNQ2 / CACNA1A / SLC2A1 with misfolding terms"],
     "how_to_find_out": "Look for UPR markers (BiP, CHOP, XBP1 splicing) in patient iPSC neurons for STXBP1, SCN1A, KCNQ2."},
]


def go_evidence(acc, go, sym):
    d = json.loads((RAW / "quickgo" / f"{acc}__{go.replace(':', '_')}.json").read_text())
    res = d["results"]
    if not res:
        raise SystemExit(f"no QuickGO annotation for {sym} {go}")
    codes = sorted({r["goEvidence"] for r in res})
    terms = sorted({r["goId"] for r in res})
    ev = [{"source": "GO", "ref": go,
           "url": f"https://www.ebi.ac.uk/QuickGO/annotations?geneProductId={acc}&goId={go}&goUsage=descendants",
           "title": f"QuickGO: {len(res)} annotation(s) of UniProtKB:{acc} ({sym}) to {', '.join(terms)}; evidence {', '.join(codes)}",
           "kind": "database", "study_type": "database_record", "extracted_by": "database", "retrieved": TODAY}]
    return ev, codes, terms


def pub_evidence(pmid, quote, st, supports=True):
    p = RAW / "pubmed" / f"{pmid}.json"
    if not p.exists():
        raise SystemExit(f"missing stored abstract for PMID {pmid}")
    r = json.loads(p.read_text())
    ok = norm(quote) in norm(r["title"] + " " + r["abstract"])
    return {"source": "PubMed", "ref": f"PMID:{pmid}", "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "title": r["title"], "year": r["year"], "quote": quote, "kind": "publication", "study_type": st,
            "supports": supports, "extracted_by": "agent-curation", "verified": ok, "retrieved": TODAY}


def main():
    graph = json.loads((ROOT / "data" / "graph.json").read_text())
    types = {n["id"]: n["type"] for n in graph["nodes"]}
    types.update({n["id"]: n["type"] for n in NEW_NODES})
    legal = {"participates_in": ("gene", "mechanism"), "has_effect": ("variant_group", "mechanism")}
    fails, edges = [], []
    for c in CLAIMS:
        s, t = legal[c["type"]]
        if types.get(c["src"]) != s or types.get(c["tgt"]) != t:
            fails.append(f"endpoint/type problem: {c['src']} -{c['type']}-> {c['tgt']}")
        ev = [pub_evidence(*x) for x in c["pubs"]]
        cev = [pub_evidence(*x, supports=False) for x in c.get("counter", [])]
        attrs = {"curated_by": "cross-family"}
        if c.get("go"):
            gev, codes, terms = go_evidence(*c["go"])
            ev = gev + ev
            attrs.update(go_evidence_codes=codes, go_terms_hit=terms)
        for e in ev + cev:
            if e.get("quote") and not e["verified"]:
                fails.append(f"quote NOT verified {e['ref']}: {e['quote'][:90]!r}")
        edge = {"id": f"{c['src']}|{c['type']}|{c['tgt']}", "source": c["src"], "target": c["tgt"], "type": c["type"],
                "label": "takes part in" if c["type"] == "participates_in" else "has effect",
                "explanation": c["expl"], "evidence_level": c["level"], "status": "supported",
                "confidence": c["conf"], "evidence": ev, "attrs": attrs}
        if cev:
            edge["counter_evidence"] = cev
        edges.append(edge)
    existing = {e["id"] for e in graph["edges"] if (e.get("attrs") or {}).get("curated_by") != "cross-family"}
    for e in edges:
        if e["id"] in existing:
            print(f"  note: {e['id']} already exists in another fragment; evidence will be merged")
    if fails:
        print("\n".join(fails))
        raise SystemExit(1)
    frag = {"nodes": NEW_NODES, "edges": edges, "clusters": [], "gaps": GAPS}
    OUT.write_text(json.dumps(frag, indent=1, ensure_ascii=False) + "\n")
    nq = sum(1 for e in edges for x in e["evidence"] + e.get("counter_evidence", []) if x.get("quote"))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(edges)} edges, {len(NEW_NODES)} new node(s); {nq}/{nq} quotes verified; "
          f"{len({x['ref'] for e in edges for x in e['evidence'] if x['source'] == 'PubMed'})} PMIDs")


if __name__ == "__main__":
    main()
