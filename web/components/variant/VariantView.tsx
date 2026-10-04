"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { Term } from "../Term";
import { EvidenceChip, WarnGlyph } from "../evidence/EvidenceBits";
import { atlasHref, diseaseHref, neighbors, type GraphIndex } from "@/lib/graph";
import { useDerived, type ModalityData } from "@/lib/derived";
import { lookupVariant, type LookupResult, type VariantsData } from "@/lib/variant";
import { CLS_PLAIN, lookupHgvs } from "@/lib/clinvar";
import { VgDirectionList } from "../direction/DirectionFlag";
import { useResource } from "@/lib/resource";
import type { AtlasEdge, AtlasNode } from "@/lib/types";

export const EXAMPLE_VARIANT = "NM_003165.6(STXBP1):c.1162C>T (p.Arg388Ter)";

const CONSEQUENCE_WORDS: Record<string, string> = {
  nonsense: "a stop signal that cuts the protein short",
  frameshift: "a change that shifts how the gene is read, usually cutting the protein short",
  splice: "a change at a splice site, which can disrupt how the gene’s message is put together",
  missense: "a swap of one protein building block for another",
  inframe_indel: "a small in-frame loss or gain of protein building blocks",
  cnv: "a deletion or duplication of a larger piece of DNA",
  synonymous: "no change to the protein",
  other: "a change whose effect can’t be read from the notation alone",
};

/** Keywords that tie a modality reason to a variant class (to list the most relevant reasons first). */
const CLASS_HINTS: Record<string, RegExp> = {
  truncating: /lost|non-functional|null|truncat|too little|haploinsuff|one copy|supplement/i,
  missense: /missense|too much|jam|dominant|gain|variant|allele|stabil|fold/i,
  splice: /splic|transcript|exon/i,
  cnv: /delet|copy|whole[- ]gene|too little|supplement/i,
};

export function VariantView() {
  return <WithGraph>{(idx) => <Variant idx={idx} />}</WithGraph>;
}

function Variant({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);
  const [seenQ, setSeenQ] = useState(q);
  if (q !== seenQ) {
    setSeenQ(q);
    setDraft(q);
  }
  const variants = useDerived<VariantsData>("variants");
  const modality = useDerived<ModalityData>("modality");
  const result = useMemo(() => (variants.status === "ready" && q.trim() ? lookupVariant(q, variants.data) : null), [variants, q]);

  return (
    <div className="mx-auto w-full max-w-[920px] px-8 pb-24 pt-10">
      <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">What does this variant mean?</h1>
      <p className="mt-2 max-w-[680px] text-[15px] leading-relaxed text-ink-3">
        Paste one line from a genetic report. The atlas looks it up among ClinVar’s pathogenic and likely-pathogenic records and
        shows what kind of change it is, the mechanism it points to, and what that can mean for research.
      </p>
      <form
        className="mt-6 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          router.replace(`/variant?q=${encodeURIComponent(draft.trim())}`, { scroll: false });
        }}
      >
        <label htmlFor="variant-q" className="sr-only">
          A line from a genetic report
        </label>
        <input
          id="variant-q"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`e.g. ${EXAMPLE_VARIANT}`}
          spellCheck={false}
          className="h-11 flex-1 rounded-lg border border-ink-4/70 bg-white px-4 text-[15px] text-ink placeholder:text-ink-3 focus:border-accent-700 focus:outline-none"
        />
        <button type="submit" className="h-11 rounded-lg bg-accent-700 px-5 text-sm font-medium text-white hover:bg-accent-900">
          Look up
        </button>
      </form>

      <p className="mt-4 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm font-medium text-warn-ink" role="note">
        This is not a diagnosis or medical advice. Discuss your report with your genetic counselor or neurologist.
      </p>

      {variants.status === "loading" && q && <p className="mt-8 text-sm text-ink-3">Loading ClinVar records…</p>}
      {variants.status === "missing" && <p className="mt-8 text-sm text-ink-3">The variant table is not available in this build ({variants.error}).</p>}
      {!q && (
        <p className="mt-8 text-sm text-ink-3">
          Try{" "}
          <button type="button" onClick={() => router.replace(`/variant?q=${encodeURIComponent(EXAMPLE_VARIANT)}`)} className="font-medium text-accent-700 hover:underline">
            {EXAMPLE_VARIANT}
          </button>
          , <span className="whitespace-nowrap">STXBP1 R388X</span> or <span className="whitespace-nowrap">SLC6A1 p.Ser295Leu</span>.
        </p>
      )}
      {result && variants.status === "ready" && (
        <Result idx={idx} r={result} scopeNote={variants.data.meta.scope_note} modality={modality.status === "ready" ? modality.data : null} />
      )}
    </div>
  );
}

function Result({ idx, r, scopeNote, modality }: { idx: GraphIndex; r: LookupResult; scopeNote: string; modality: ModalityData | null }) {
  const gene = r.matches[0]?.gene ?? r.query.gene;
  const geneNode = gene ? idx.nodeById.get(`gene:${gene}`) : undefined;
  const disease = geneNode
    ? neighbors(idx, geneNode.id, { relations: ["causes"], direction: "out" }).map((n) => idx.nodeById.get(n.other)).find((n): n is AtlasNode => !!n)
    : undefined;
  const vgId = r.matches[0]?.variant_group ?? r.fallback?.variant_group ?? null;
  const consequence = r.matches[0]?.consequence ?? r.fallback?.consequence ?? null;
  const vgSlug = vgId?.split(":")[2] ?? "";

  if (r.status === "unparsed") {
    return (
      <div className="mt-8">
      <Card title="We couldn’t find a variant in that text">
        <p className="text-sm leading-relaxed text-ink-2">
          Look on the report for a line with <b>c.</b> (the DNA change) or <b>p.</b> (the protein change), usually next to the gene name, for
          example <span className="whitespace-nowrap">{EXAMPLE_VARIANT}</span>.
        </p>
      </Card>
      </div>
    );
  }
  if (r.status === "gene_not_in_atlas" && r.query.non_slice_gene) {
    return <ClinvarFallback gene={r.query.non_slice_gene} c={r.query.c} p={r.query.p} />;
  }

  return (
    <div className="mt-8 space-y-6">
      <Card
        title={
          r.status === "clinvar_match"
            ? "Found in ClinVar"
            : r.status === "not_in_clinvar_plp"
              ? "Not among ClinVar’s pathogenic records"
              : "Variant read, but no gene given"
        }
      >
        <dl className="divide-y divide-line-2">
          {gene && (
            <Row k="Gene and disease">
              <span className="font-medium">{gene}</span>
              {disease && (
                <>
                  {" · "}
                  <Link href={diseaseHref(disease.id)} className="text-accent-700 hover:underline">
                    {disease.label}
                  </Link>
                </>
              )}
            </Row>
          )}
          {r.matches.map((m) => (
            <Row key={m.accession} k="ClinVar record">
              <p className="break-words text-ink">{m.hgvs}</p>
              <p className="mt-1 text-sm text-ink-2">
                <b className="font-medium">{m.classification}</b> · {m.consequence.replace("_", " ")}, {CONSEQUENCE_WORDS[m.consequence] ?? ""} ·{" "}
                {m.stars}★ review · {m.n_submissions} submission{m.n_submissions === 1 ? "" : "s"}
              </p>
              <a href={m.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-sm font-medium text-accent-700 hover:underline">
                Open {m.accession} in ClinVar ↗
              </a>
            </Row>
          ))}
          {r.fallback && (
            <Row k="Type of change (inferred)">
              <p className="text-ink">
                <b className="font-medium">{r.fallback.consequence.replace("_", " ")}</b>: {CONSEQUENCE_WORDS[r.fallback.consequence] ?? ""}{" "}
                <span className="rounded border border-dashed border-ink-4 px-1.5 py-px text-[11px] text-ink-3">inferred · {r.fallback.certainty}</span>
              </p>
              <p className="mt-1 text-sm text-ink-3">The type shown is read from the notation only ({r.fallback.note}).</p>
              {r.fallback.consequence === "cnv" && (
                <p className="mt-1 text-sm text-ink-3">A larger deletion can remove neighbouring genes too; the notation alone can’t tell which case applies.</p>
              )}
            </Row>
          )}
        </dl>
        {r.warnings.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {r.warnings.map((w) => (
              <li key={w} className="flex gap-2 text-sm text-warn-ink">
                <span className="mt-0.5 shrink-0">
                  <WarnGlyph />
                </span>
                {w}
              </li>
            ))}
          </ul>
        )}
        {r.status !== "clinvar_match" && <p className="mt-3 text-xs text-ink-3">{scopeNote}</p>}
      </Card>

      {vgId && <MechanismCard idx={idx} vgId={vgId} diseaseId={disease?.id} />}
      {vgId && gene && (
        <div className="rounded-lg border border-line px-6 py-4 empty:hidden">
          <VgDirectionList gene={gene} vgId={vgId} />
        </div>
      )}
      {disease && modality?.assessments[disease.id] && consequence && (
        <TherapyCard modality={modality} diseaseId={disease.id} vgSlug={vgSlug} consequence={consequence} />
      )}
      {vgId && geneNode && <SameGeneCard idx={idx} geneId={geneNode.id} vgId={vgId} />}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-2 py-3 md:grid-cols-[170px_minmax(0,1fr)]">
      <dt className="text-sm text-ink-3">{k}</dt>
      <dd className="text-[15px]">{children}</dd>
    </div>
  );
}

function effectsOf(idx: GraphIndex, vgId: string): AtlasEdge[] {
  return neighbors(idx, vgId, { relations: ["has_effect"], direction: "out" }).map((n) => n.edge);
}

function MechanismCard({ idx, vgId, diseaseId }: { idx: GraphIndex; vgId: string; diseaseId?: string }) {
  const vg = idx.nodeById.get(vgId);
  const effects = effectsOf(idx, vgId);
  const minority = new Set(
    diseaseId
      ? neighbors(idx, diseaseId, { relations: ["driven_by"], direction: "out" })
          .filter((n) => n.edge.attrs?.minority_mechanism === true)
          .map((n) => n.other)
      : [],
  );
  return (
    <section className="rounded-lg border border-line px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">What it points to</h2>
      <p className="mt-1 text-sm text-ink-3">
        The variant belongs to the group{" "}
        <Link href={atlasHref(vgId)} className="font-medium text-accent-700 hover:underline">
          {vg?.label ?? vgId}
        </Link>
        . In the atlas, that group leads to:
      </p>
      {effects.length ? (
        <ul className="mt-3 space-y-2">
          {effects.map((e) => {
            const m = idx.nodeById.get(e.target);
            return (
              <li key={e.id} className="flex flex-wrap items-center gap-2">
                <span className="text-[15px] text-ink">{m ? <Term>{m.label}</Term> : e.target}</span>
                <EvidenceChip edge={e} />
                {e.status === "contested" && <span className="text-xs font-medium text-warn-ink">contested: sources disagree</span>}
                {minority.has(e.target) && <span className="text-xs font-medium text-warn-ink">a minority view for this disease</span>}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-ink-3">No mechanism is recorded for this group yet.</p>
      )}
    </section>
  );
}

function TherapyCard({ modality, diseaseId, vgSlug, consequence }: { modality: ModalityData; diseaseId: string; vgSlug: string; consequence: string }) {
  const a = modality.assessments[diseaseId];
  const cls = vgSlug.includes("deletion") ? "cnv" : vgSlug || (consequence === "missense" ? "missense" : "truncating");
  const hint = CLASS_HINTS[cls] ?? CLASS_HINTS.truncating;
  return (
    <section className="rounded-lg border border-line px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">What this can mean for therapy approaches</h2>
      <p className="mt-1 text-sm text-ink-3">
        A rule-based screen of how each approach fits this disease’s mechanism, with the reasons most relevant to a {cls} change listed
        first. It is never a recommendation.
      </p>
      <ul className="mt-4 divide-y divide-line-2 border-y border-line-2">
        {modality.modalities.map((mod) => {
          const cell = a.modalities[mod.id];
          if (!cell) return null;
          const reasons = [...cell.reasons].sort((x, y) => Number(hint.test(y.text)) - Number(hint.test(x.text))).slice(0, 2);
          return (
            <li key={mod.id} className="grid grid-cols-1 gap-2 py-3 md:grid-cols-[220px_minmax(0,1fr)]">
              <div>
                <p className="text-sm font-medium text-ink">{mod.label}</p>
                <FitBadge fit={cell.fit} />
              </div>
              <ul className="space-y-1 text-sm leading-relaxed text-ink-2">
                {reasons.map((r) => (
                  <li key={r.rule}>
                    {r.text} <span className="text-xs text-ink-3">({r.rule})</span>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        <span className="font-medium">{modality.status}.</span> {modality.not_advice}{" "}
        <Link href={`/approach?disease=${encodeURIComponent(diseaseId)}`} className="text-accent-700 hover:underline">
          See the full reasoning →
        </Link>
      </p>
    </section>
  );
}

export function FitBadge({ fit }: { fit: string }) {
  const cls: Record<string, string> = {
    good: "border-[#bcd9c6] bg-[#edf6f0] text-ok",
    conditional: "border-accent-200 bg-accent-50 text-accent-900",
    poor: "border-warn-line bg-warn-bg text-warn-ink",
    not_assessed: "border-line bg-subtle text-ink-3",
  };
  const label: Record<string, string> = { good: "Good fit", conditional: "Conditional", poor: "Poor fit", not_assessed: "Not assessed" };
  return <span className={`mt-1 inline-flex rounded border px-1.5 py-px text-[11px] font-medium ${cls[fit] ?? cls.not_assessed}`}>{label[fit] ?? fit}</span>;
}

function SameGeneCard({ idx, geneId, vgId }: { idx: GraphIndex; geneId: string; vgId: string }) {
  const mine = new Set(effectsOf(idx, vgId).map((e) => e.target));
  const others = neighbors(idx, geneId, { relations: ["variant_in"], direction: "in" })
    .map((n) => idx.nodeById.get(n.other))
    .filter((n): n is AtlasNode => !!n && n.id !== vgId)
    .map((vg) => ({ vg, effects: effectsOf(idx, vg.id).filter((e) => !mine.has(e.target)) }))
    .filter((x) => x.effects.length);
  const gene = idx.nodeById.get(geneId)?.label ?? geneId;
  return (
    <section className="rounded-lg border border-line px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">Same gene, different mechanism</h2>
      <p className="mt-1 text-sm text-ink-3">
        Other kinds of {gene} changes act differently in the atlas. This is why the exact variant, not just the gene name, decides which
        research and which approaches apply.
      </p>
      {others.length ? (
        <ul className="mt-3 space-y-3">
          {others.map(({ vg, effects }) => (
            <li key={vg.id}>
              <p className="text-sm font-medium text-ink">{vg.label}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {effects.map((e) => (
                  <span key={e.id} className="inline-flex items-center gap-1.5 text-sm text-ink-2">
                    → {idx.nodeById.get(e.target)?.label ?? e.target}
                    <EvidenceChip edge={e} />
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-ink-3">In the atlas, the other {gene} variant groups point to the same mechanisms as this one.</p>
      )}
    </section>
  );
}

const STARS_PLAIN: Record<number, string> = { 4: "practice guideline", 3: "reviewed by an expert panel", 2: "several labs agree", 1: "one lab", 0: "no review criteria" };
const CV_WORDS: Record<string, string> = {
  frameshift: "a frameshift: the gene is read out of step, so the protein is usually cut short",
  nonsense: "an early stop: the protein is usually cut short",
  missense: "a missense change: one building block of the protein is swapped",
  splice_canonical: "a change at a splice site, where the gene’s pieces are joined",
  splice_region: "a change near a splice site",
  start_lost: "a change that removes the start signal",
  stop_lost: "a change that removes the stop signal",
};

/** Genes outside the in-depth atlas: look the line up in the full ClinVar P/LP shard for that gene. */
function ClinvarFallback({ gene, c, p }: { gene: string; c: string | null; p: string | null }) {
  const key = `cv-hgvs:${gene}:${c ?? ""}:${p ?? ""}`;
  const res = useResource(key, () => lookupHgvs(gene, c, p));
  const d = res?.data;
  const search = `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(`${gene}[gene]${c ? ` AND "${c}"` : ""}`)}`;
  if (!d) return <p className="mt-8 text-sm text-ink-3">Looking {gene} up in ClinVar…</p>;
  return (
    <div className="mt-8 space-y-6">
      <Card title={d.hits.length ? "Found in ClinVar" : d.geneKnown ? "Not among ClinVar’s pathogenic records" : `${gene} has no disease-causing record in ClinVar`}>
        {d.hits.length ? (
          <div className="space-y-3 text-sm leading-relaxed text-ink-2">
            {d.hits.slice(0, 3).map((h) => (
              <div key={h.vid}>
                <p className="break-all font-mono text-[15px] font-semibold text-ink">{h.name}</p>
                <p>
                  ClinVar lists it as <b className="font-medium text-ink">{CLS_PLAIN[h.cls]?.toLowerCase()}</b> ({STARS_PLAIN[h.stars] ?? `${h.stars} stars`}).
                  {CV_WORDS[h.consequence] ? ` It is ${CV_WORDS[h.consequence]}.` : ""}{" "}
                  <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                    See it in ClinVar (variation {h.vid}) ↗
                  </a>
                </p>
              </div>
            ))}
            {d.on === "p" && <p className="text-warn-ink">Matched on the protein change only; confirm the DNA change and transcript with your genetic counsellor.</p>}
          </div>
        ) : (
          <p className="text-sm leading-relaxed text-ink-2">
            {d.geneKnown
              ? `This change is not among the changes ClinVar lists as disease-causing for ${gene}. That does not mean it is harmless; it may be uncertain, new, or written differently.`
              : `We found no pathogenic or likely-pathogenic record for ${gene} in ClinVar. Check the spelling of the gene.`}{" "}
            <a href={search} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              Search ClinVar ↗
            </a>
          </p>
        )}
        <p className="mt-3 text-xs text-ink-3">
          {gene} is outside the genes the atlas maps in depth, so there is no mechanism or treatment view here. Source: ClinVar pathogenic / likely-pathogenic records (2026-09-29).
        </p>
      </Card>
    </div>
  );
}
