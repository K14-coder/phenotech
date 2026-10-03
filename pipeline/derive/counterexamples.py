"""Product 5: where the clean pattern breaks -> data/derived/counterexamples.json

Run:  python3 pipeline/derive/counterexamples.py
Every edge_id is checked against data/graph.json and the run fails if one is missing, so this file
cannot drift away from the graph. Numbers in the text are pulled from the graph and from
data/derived/variants.json rather than typed by hand.
"""
from __future__ import annotations

from dcommon import DERIVED, TODAY, Graph, read_json, write_json


def main():
    g = Graph()
    v = read_json(DERIVED / "variants.json")
    E = g.edges

    def conf(eid):
        return E[eid]["confidence"]

    def n_counter(eid):
        return len(E[eid].get("counter_evidence") or [])

    unc13a_cds = g.nodes["gene:UNC13A"]["attrs"]["cds_length_bp"]
    cplx1_multi = g.nodes["vg:CPLX1:contiguous-gene-deletion"]["attrs"]["clinvar_total_in_group"]
    cplx1_total = g.nodes["vg:CPLX1:contiguous-gene-deletion"]["attrs"]["clinvar_gene_total_PLP"]
    stx1a_multi = g.nodes["vg:STX1A:contiguous-gene-deletion"]["attrs"]["clinvar_total_in_group"]
    stx1a_total = g.nodes["vg:STX1A:contiguous-gene-deletion"]["attrs"]["clinvar_gene_total_PLP"]
    inferred = sorted(e["id"] for e in E.values()
                      if e["type"] == "has_effect" and e["evidence_level"] == "inferred"
                      and e["status"] == "unverified")
    pheno_no_distinctive = sorted(
        e["id"] for e in E.values()
        if e["type"] == "similar_phenotype" and not e.get("attrs", {}).get("shared_distinctive"))
    bridge = "disease:STXBP1|shares_mechanism|disease:SLC6A1"

    items = [
        {
            "id": "cx:snap25-opposite-direction-variants",
            "title": "One gene, two opposite problems: SNAP25 I67N and V48F (and the minority reports the atlas keeps)",
            "plain_language": ("In SNAP25, one change makes the nerve ending release too little, and a different "
                              "change makes it release too much at rest. A drug that pushes release harder could "
                              "help the first child and hurt the second."),
            "why_it_matters": ("It breaks the idea that a gene has one mechanism and therefore one therapy. The "
                               "atlas carries loss-of-function and gain-of-function edges for the same disease, and "
                               "the aminopyridine edge is marked contested for exactly this reason. A family's "
                               "specific variant, not the gene name, decides the direction. The same pattern is "
                               "flagged for SYT1, where the haploinsufficiency and gain-of-function edges are kept "
                               "as minority mechanisms rather than dropped - minority readings are where the next "
                               "correction usually comes from."),
            "edge_ids": ["disease:SNAP25|driven_by|mech:loss-of-function",
                         "disease:SNAP25|driven_by|mech:gain-of-function",
                         "vg:SNAP25:missense|has_effect|mech:gain-of-function",
                         "therapy:aminopyridine-presynaptic-boost|developed_for|disease:SNAP25",
                         "disease:SYT1|driven_by|mech:haploinsufficiency",
                         "disease:SYT1|driven_by|mech:gain-of-function"],
        },
        {
            "id": "cx:stx1b-both-directions",
            "title": "STX1B variants point both ways, and one does both at once",
            "plain_language": ("For STX1B, one change leaves fewer vesicles ready to go, another makes fusion "
                               "easier, and in patient-derived neurons a third change does both at the same time."),
            "why_it_matters": ("Both the loss-of-function and the gain-of-function edge for STX1B are contested in "
                               f"the graph (the loss-of-function edge carries {n_counter('disease:STX1B|driven_by|mech:loss-of-function')} "
                               "contradicting items). Any plan that treats 'STX1B epilepsy' as one entity is "
                               "treating at least two."),
            "edge_ids": ["disease:STX1B|driven_by|mech:loss-of-function",
                         "disease:STX1B|driven_by|mech:gain-of-function",
                         "vg:STX1B:truncating|has_effect|mech:haploinsufficiency"],
        },
        {
            "id": "cx:stxbp1-aav-trial-terminated",
            "title": "The first STXBP1 gene-therapy trial was stopped",
            "plain_language": ("A gene therapy for STXBP1 reached children in a clinical trial, and that trial was "
                               "terminated because a stopping rule was met. The same sponsor's natural-history study "
                               "was withdrawn before anyone enrolled."),
            "why_it_matters": ("The graph shows gene replacement for STXBP1 as contested, not as a live option, and "
                               "the preclinical paper says plainly that no human evidence defines how much protein "
                               "is enough. Hope in a knowledge graph has to carry its counter-evidence, or families "
                               "read a terminated programme as an available treatment."),
            "edge_ids": (["therapy:aav-stxbp1-gene-replacement|developed_for|disease:STXBP1",
                          "therapy:aav-stxbp1-gene-replacement|targets|mech:haploinsufficiency"]
                         + sorted(e["id"] for e in E.values()
                                  if "NCT06983158" in e["id"] or "NCT05462054" in e["id"])),
        },
        {
            "id": "cx:stxbp1-mechanism-unsettled",
            "title": "Nobody agrees what STXBP1 variants actually do",
            "plain_language": ("For the best-studied gene in this group, experts still disagree: does the faulty "
                               "protein simply go missing, or does it actively jam the healthy copy? Different "
                               "experiments say different things."),
            "why_it_matters": ("The answer decides whether adding a healthy gene copy can work at all. All three "
                               "STXBP1 mechanism edges are contested "
                               f"(haploinsufficiency {conf('disease:STXBP1|driven_by|mech:haploinsufficiency')}, "
                               f"destabilization {conf('disease:STXBP1|driven_by|mech:protein-destabilization')}, "
                               f"dominant-negative {conf('disease:STXBP1|driven_by|mech:dominant-negative')}), and "
                               "the cluster that groups 'the altered protein jams the machine' deliberately includes "
                               "STXBP1 as a contested member."),
            "edge_ids": ["disease:STXBP1|driven_by|mech:haploinsufficiency",
                         "disease:STXBP1|driven_by|mech:protein-destabilization",
                         "disease:STXBP1|driven_by|mech:dominant-negative",
                         "vg:STXBP1:missense|has_effect|mech:dominant-negative",
                         "disease:STXBP1|driven_by|mech:gain-of-function"],
        },
        {
            "id": "cx:bridge-contested",
            "title": "The headline bridge between STXBP1 and SLC6A1 is contested",
            "plain_language": ("One trial already enrols children with either an STXBP1 or an SLC6A1 change, on the "
                               "idea that both make an unstable protein that a chaperone drug could rescue. The two "
                               "proteins are unstable in different ways, and the drug may partly work by helping the "
                               "healthy copy rather than fixing the faulty one."),
            "why_it_matters": (f"This is the most interesting edge in the atlas and it carries {n_counter(bridge)} "
                               "contradicting items. If the shared mechanism is really two different stories joined "
                               "by one convenient drug, the cross-gene trial design is weaker than it looks - and "
                               "that is a question for a biochemist, not a graph."),
            "edge_ids": [bridge,
                         "disease:SLC6A1|driven_by|mech:protein-destabilization",
                         "vg:SLC6A1:missense|has_effect|mech:protein-destabilization",
                         "therapy:4-phenylbutyrate|targets|mech:protein-destabilization",
                         "therapy:4-phenylbutyrate|developed_for|disease:SLC6A1"],
        },
        {
            "id": "cx:nsf-model-organism-only",
            "title": "NSF sits in the 'jammed machine' cluster on the strength of a fly eye",
            "plain_language": ("NSF is placed next to the other genes because two changes looked like they blocked "
                               "the machinery. That conclusion comes from an experiment in fruit-fly eyes, from a "
                               "single report, and has never been repeated in nerve cells."),
            "why_it_matters": ("Cluster membership is an inference, not a measurement. The gene-to-disease edge "
                               f"itself has confidence {conf('gene:NSF|causes|disease:NSF')}, and the phenotype "
                               "similarity metric nevertheless makes NSF the closest match to UNC13A in the whole "
                               "slice - so a weak mechanism claim and a strong phenotype signal disagree."),
            "edge_ids": ["disease:NSF|driven_by|mech:dominant-negative",
                         "vg:NSF:missense|has_effect|mech:dominant-negative",
                         "gene:NSF|causes|disease:NSF",
                         "disease:UNC13A|similar_phenotype|disease:NSF"],
        },
        {
            "id": "cx:unc13a-too-big-for-aav",
            "title": f"UNC13A does not fit in the standard gene-therapy virus ({unc13a_cds} bp)",
            "plain_language": ("The usual gene-therapy virus can only carry a gene of a certain size. The UNC13A "
                               "instruction is too long to fit, so the standard 'deliver a healthy copy' approach is "
                               "not available for this gene, however well it might match the biology."),
            "why_it_matters": ("A physical constraint beats a mechanism argument. Every other gene in the slice fits; "
                               "UNC13A is the one where the family-facing answer has to be different. The only "
                               "UNC13A-directed molecule in the atlas is an oligonucleotide developed for ALS, not "
                               "for the Mendelian disorder."),
            "edge_ids": ["gene:UNC13A|causes|disease:UNC13A",
                         "therapy:unc13a-splice-switching-aso|developed_for|disease:UNC13A",
                         "therapy:unc13a-splice-switching-aso|targets|mech:synaptic-vesicle-priming",
                         "vg:UNC13A:truncating|has_effect|mech:haploinsufficiency"],
        },
        {
            "id": "cx:cplx1-counts-are-not-about-cplx1",
            "title": f"{cplx1_multi} of CPLX1's {cplx1_total} pathogenic records are deletions of several genes at once",
            "plain_language": ("A database search for CPLX1 returns many 'pathogenic' results, but almost all of them "
                               "are large deletions that remove CPLX1 together with many neighbouring genes. They "
                               "say little about CPLX1 itself."),
            "why_it_matters": ("Counting records would make CPLX1 look well understood. The atlas gives the "
                               "multi-gene group a variant_in edge but deliberately no mechanism edge, and the one "
                               "CPLX1 mechanism edge that exists rests on two truncating records and an inferred "
                               f"effect (confidence {conf('vg:CPLX1:truncating|has_effect|mech:haploinsufficiency')}). "
                               f"STX1A has the same problem: {stx1a_multi} of {stx1a_total} records are "
                               "Williams-region copy-number changes."),
            "edge_ids": ["vg:CPLX1:contiguous-gene-deletion|variant_in|gene:CPLX1",
                         "vg:CPLX1:truncating|has_effect|mech:haploinsufficiency",
                         "vg:STX1A:contiguous-gene-deletion|variant_in|gene:STX1A",
                         "gene:STX1A|causes|disease:STX1A"],
        },
        {
            "id": "cx:looking-alike-is-not-sharing-a-cause",
            "title": "The pair with the strongest symptom match shares no distinctive feature",
            "plain_language": ("Two conditions can score as very similar because they share common things like "
                               "seizures, low muscle tone and developmental delay. Sharing those does not mean they "
                               "share a cause."),
            "why_it_matters": ("Phenotype similarity is computed, not observed: "
                               f"{len(pheno_no_distinctive)} of the slice's similarity edges have an empty list of "
                               "shared DISTINCTIVE features, so the match is carried entirely by broad terms. The "
                               "edges are kept with low confidence and the explanation names which shared features "
                               "are broad, which is the only honest way to show them."),
            "edge_ids": pheno_no_distinctive + ["disease:STXBP1|similar_phenotype|disease:SLC6A1"],
        },
        {
            "id": "cx:truncating-to-haploinsufficiency-is-assumed",
            "title": f"{len(inferred)} 'broken copy means missing protein' edges are assumptions, not experiments",
            "plain_language": ("When a change clearly breaks the gene, the atlas assumes the result is 'not enough "
                               "protein'. For most genes here, no experiment has checked that in a human nerve cell."),
            "why_it_matters": ("These edges are labelled inferred and unverified with confidence 0.45 on purpose. "
                               "They are the quiet majority of the mechanism layer, and anything built on top of "
                               "them - including the modality screen and the hypotheses - inherits that weakness."),
            "edge_ids": inferred,
        },
    ]

    missing = [(it["id"], eid) for it in items for eid in it["edge_ids"] if eid not in E]
    if missing:
        raise SystemExit(f"edge ids not in graph: {missing}")
    for it in items:
        it["edges"] = [{"id": eid, "type": E[eid]["type"], "status": E[eid]["status"],
                        "evidence_level": E[eid]["evidence_level"], "confidence": E[eid]["confidence"],
                        "n_counter_evidence": n_counter(eid)} for eid in it["edge_ids"]]
    out = {
        "about": ("The places where the clean story breaks. Each item names edges that exist in data/graph.json, so "
                  "a reader can open the evidence. Written for families first: the plain_language line should be "
                  "readable by a parent, and the why_it_matters line says what it changes."),
        "meta": {"generated": TODAY, "graph": g.meta.get("generated_at"), "n_items": len(items),
                 "code": "pipeline/derive/counterexamples.py",
                 "integrity": "the build fails if any edge_id is absent from the graph"},
        "items": items,
    }
    size = write_json(DERIVED / "counterexamples.json", out)
    print(f"[counterexamples] {len(items)} items, "
          f"{sum(len(i['edge_ids']) for i in items)} edge references, all resolve ({size / 1024:.0f} KB)")
    for it in items:
        print(f"  {it['id']:48s} {len(it['edge_ids'])} edges")


if __name__ == "__main__":
    main()
