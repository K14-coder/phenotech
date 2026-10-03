"use client";

import Link from "next/link";
import { WithGraph } from "../GraphProvider";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { IdeaCard, ideasFor } from "./IdeaCard";
import { atlasHref, diseaseHref, type GraphIndex } from "@/lib/graph";
import { useDerived, type OpportunityPair } from "@/lib/derived";

interface Opportunities {
  model_and_assay_transfer: { rule: string; n_pairs: number; strongest_pairs_both_driven_by: OpportunityPair[] };
  computed_candidates_rejected_on_review: {
    rule: string;
    items: { therapy_label: string; disease: string; disease_label: string; mechanism_label: string; review_rejection: string }[];
  };
}

export function IdeasView() {
  return <WithGraph>{(idx) => <Ideas idx={idx} />}</WithGraph>;
}

function Ideas({ idx }: { idx: GraphIndex }) {
  const ideas = ideasFor(idx);
  const opp = useDerived<Opportunities>("opportunities");
  return (
    <div className="mx-auto w-full max-w-[1040px] px-8 pb-24 pt-10">
      <p className="text-sm text-ink-3">Dots nobody connected</p>
      <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.02em] text-ink">Ideas worth testing</h1>
      <p className="mt-2 max-w-[720px] text-[15px] leading-relaxed text-ink-3">
        Hypotheses, not evidence. The atlas proposes a therapy only where a mechanism links it to a disease and nobody has developed or tested it
        there. Each idea names its weakest link and a test that could prove it wrong.
      </p>

      <div className="mt-8 space-y-4">
        {ideas.map((e) => (
          <IdeaCard key={e.id} idx={idx} edge={e} />
        ))}
        {!ideas.length && <p className="text-sm text-ink-3">No hypotheses in this data.</p>}
      </div>

      {opp.status === "ready" && (
        <>
          <section className="mt-14" aria-labelledby="transfer-h">
            <h2 id="transfer-h" className="text-[22px] font-semibold tracking-tight text-ink">
              Models and assays that could be reused
            </h2>
            <p className="mt-2 max-w-[720px] text-sm leading-relaxed text-ink-3">
              Two diseases share an effect mechanism; one has a model, assay, biobank or outcome measure and the other has none. This is a
              list of opportunities, not findings.
            </p>
            <ul className="mt-4 space-y-2.5">
              {opp.data.model_and_assay_transfer.strongest_pairs_both_driven_by.slice(0, 8).map((p) => (
                <li key={`${p.shared_mechanism}-${p.has_model}-${p.lacks_model}`} className="rounded-lg border border-line px-5 py-3.5">
                  <p className="text-sm text-ink">
                    <Link href={diseaseHref(p.has_model)} className="font-medium hover:text-accent-700">
                      {p.has_model_label}
                    </Link>{" "}
                    → {p.lacks_model ? <Link href={diseaseHref(p.lacks_model)} className="font-medium hover:text-accent-700">{p.lacks_model_label}</Link> : "?"}
                    <span className="text-ink-3"> · shared: {p.shared_mechanism_label}</span>
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {p.assets.slice(0, 4).map((a) => {
                      const e = idx.edgeById.get(a.edge_id);
                      return e ? (
                        <EvidenceChip key={a.asset} edge={e} label={a.label} />
                      ) : (
                        <Link key={a.asset} href={atlasHref(a.asset)} className="text-xs text-accent-700 hover:underline">
                          {a.label}
                        </Link>
                      );
                    })}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-14" aria-labelledby="rejected-h">
            <h2 id="rejected-h" className="text-[22px] font-semibold tracking-tight text-ink">
              Rejected on review
            </h2>
            <p className="mt-2 max-w-[720px] text-sm leading-relaxed text-ink-3">
              Candidates that passed the graph search but a human read of the biology threw out. Kept visible as worked examples.
            </p>
            <ul className="mt-4 space-y-2.5">
              {opp.data.computed_candidates_rejected_on_review.items.map((r) => (
                <li key={r.therapy_label + r.disease} className="rounded-lg border border-line px-5 py-3.5">
                  <p className="text-sm font-medium text-ink">
                    {r.therapy_label} → {r.disease_label}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">{r.review_rejection}</p>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
