// AI tasks: prompt context is rebuilt on the server from graph.json (never trusted from the browser),
// every connection gets a short citation ref ("E3"), and the model's citations are mapped back to
// real edge ids and validated. Pure module: used by app/api/ai/generate and nothing in the browser.
import { shortestEvidencePath, type GraphIndex } from "./graph";
import {
  closestDiseases,
  diseaseContext,
  existingWork,
  gapsForDisease,
  communitiesFor,
  REUSE_META,
  relatedOrgsFor,
  researcherPartners,
  suggestNextStep,
} from "./insights";
import { EVIDENCE_LEVEL_META, TYPE_LABEL, ASSET_KIND_LABEL, relationSentence } from "./text";
import type { AtlasEdge, AtlasNode } from "./types";
import { compareAiId, pathAiId, type AiDoc } from "./ai-shared";
import { compareDiseases, spectrumWords } from "./compare";

export const AI_KINDS = ["explain-path", "proposal", "compare-questions", "experiment", "outreach"] as const;
export type AiKind = (typeof AI_KINDS)[number];

/** Output shape for every kind (strict JSON Schema: all properties required, no extras). */
export const AI_DOC_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["title", "sections"],
  properties: {
    title: { type: "string" },
    sections: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["heading", "sentences"],
        properties: {
          heading: { type: "string" },
          sentences: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              required: ["text", "edge_ids"],
              properties: {
                text: { type: "string" },
                edge_ids: { type: "array", items: { type: "string" } },
              },
            },
          },
        },
      },
    },
  },
} as const;


export interface AiTask {
  kind: AiKind;
  id: string;
  instructions: string;
  input: string;
  /** citation ref ("E1") -> edge id */
  refs: Map<string, string>;
}

export type TaskResult = { task: AiTask } | { error: string; status: number };

// ---------- shared context helpers ----------

class RefBook {
  refs = new Map<string, string>(); // ref -> edge id
  byEdge = new Map<string, string>(); // edge id -> ref
  edges: AtlasEdge[] = [];
  constructor(private max = 48) {}
  ref(e: AtlasEdge | undefined): string | null {
    if (!e) return null;
    const have = this.byEdge.get(e.id);
    if (have) return have;
    if (this.edges.length >= this.max) return null;
    const r = `E${this.edges.length + 1}`;
    this.refs.set(r, e.id);
    this.byEdge.set(e.id, r);
    this.edges.push(e);
    return r;
  }
  refsOf(edges: (AtlasEdge | undefined)[]): string[] {
    return edges.map((e) => this.ref(e)).filter((r): r is string => !!r);
  }
}

function describeEdge(idx: GraphIndex, e: AtlasEdge, ref: string) {
  const supporting = e.evidence.filter((ev) => ev.supports !== false);
  const limiting = [...e.evidence.filter((ev) => ev.supports === false), ...(e.counter_evidence ?? [])];
  const quotes = [...supporting]
    .filter((ev) => typeof ev.quote === "string" && ev.quote.trim())
    .sort((a, b) => Number(!!b.verified) - Number(!!a.verified))
    .slice(0, 2)
    .map((ev) => ({ source: ev.source, ref: ev.ref, verified: !!ev.verified, quote: ev.quote!.slice(0, 400) }));
  return {
    ref,
    statement: relationSentence(e, idx.nodeById.get(e.source), idx.nodeById.get(e.target)),
    explanation: e.explanation,
    evidence_level: EVIDENCE_LEVEL_META[e.evidence_level]?.label ?? e.evidence_level,
    confidence: Number(e.confidence.toFixed(2)),
    status: e.status,
    sources: supporting.length,
    quotes,
    contradicting_or_limiting: limiting.length,
    ...(limiting[0]?.quote ? { limiting_quote: limiting[0].quote.slice(0, 300) } : {}),
  };
}

function nodeBrief(n: AtlasNode | undefined) {
  return n ? { name: n.label, type: TYPE_LABEL[n.type]?.one ?? n.type } : null;
}

// ---------- explain-path ----------

const EXPLAIN_PATH_INSTRUCTIONS = `You explain one route through a rare-disease knowledge graph to a parent who has no medical or science background.
Rules:
- Use only the facts in the input JSON. Do not add facts, numbers, names, treatments, timelines or promises.
- Under 150 words in total. Short sentences and everyday words. If a technical term is unavoidable, explain it in the same sentence.
- Walk through the route in order, from "from" to "to".
- Every sentence that states a fact must list in edge_ids the refs (like "E2") of the steps it relies on. A sentence that only frames or links ideas may have an empty edge_ids list. Never write the refs themselves (E1, E2, ...) in the text: put them only in edge_ids.
- Say clearly what is uncertain: name any step whose evidence_level is "Inferred by atlas" or "Hypothesis", any step whose status is "contested" or "unverified", and any step with confidence below 0.5. Say that a route is only as strong as its weakest step.
- Do not give medical advice.
Output: a short title (under 10 words) and 1 to 3 sections, each with a short heading and its sentences.`;

export function buildExplainPathTask(idx: GraphIndex, payload: unknown): TaskResult {
  const p = (payload ?? {}) as { from?: unknown; to?: unknown; includeHypotheses?: unknown };
  const from = typeof p.from === "string" ? p.from : "";
  const to = typeof p.to === "string" ? p.to : "";
  const includeHypotheses = p.includeHypotheses === true;
  if (!idx.nodeById.has(from) || !idx.nodeById.has(to)) return { error: "Unknown from/to node.", status: 404 };
  const route = shortestEvidencePath(idx, from, to, { includeHypotheses });
  if (!route || !route.steps.length) return { error: "No route between these nodes.", status: 404 };

  const book = new RefBook();
  const steps = route.steps.map((s) => {
    const ref = book.ref(s.edge)!;
    return { ...describeEdge(idx, s.edge, ref), from: idx.nodeById.get(s.from)?.label, to: idx.nodeById.get(s.to)?.label };
  });
  const input = {
    from: nodeBrief(idx.nodeById.get(from)),
    to: nodeBrief(idx.nodeById.get(to)),
    number_of_steps: steps.length,
    weakest_step: route.weakest ? { ref: book.byEdge.get(route.weakest.id), confidence: route.weakest.confidence } : null,
    steps,
  };
  return {
    task: {
      kind: "explain-path",
      id: pathAiId(from, to, includeHypotheses),
      instructions: EXPLAIN_PATH_INSTRUCTIONS,
      input: JSON.stringify(input, null, 1),
      refs: book.refs,
    },
  };
}

// ---------- proposal ----------

export const PROPOSAL_HEADINGS = [
  "Why our communities are connected",
  "What already exists that we could share",
  "What must be checked before we join forces",
  "Proposed first step this month",
  "What we don't know yet",
  "Short outreach email",
];

const PROPOSAL_INSTRUCTIONS = `You draft a one-page collaboration proposal written by a patient-group leader for the community affected by the focus disease, addressed to the partner named in the input. Readers are not scientists.
Rules:
- Use only the facts in the input JSON. Never invent organizations, people, contact details, numbers, dates, study results or funding.
- Use exactly these section headings, in this order: ${PROPOSAL_HEADINGS.map((h) => `"${h}"`).join(", ")}.
- Every sentence that states a fact must list in edge_ids the refs (like "E4") of the connections it relies on. Framing sentences (greetings, transitions, the ask) may have an empty edge_ids list. Never write the refs themselves (E1, E2, ...) in the text: put them only in edge_ids.
- Be honest about uncertainty: say when a connection is inferred by the atlas, a hypothesis, contested, unverified or below 0.5 confidence.
- "What must be checked before we join forces" must cover the differences and checks listed in the input.
- "What we don't know yet" must restate the open questions from the input. If there are none, say that none are recorded yet.
- "Proposed first step this month" is one concrete, small action based on the suggested next step.
- "Short outreach email": 4 to 7 sentences addressed to the partner, signed "[Your name], on behalf of" the sender. No contact details.
- Never give medical or treatment advice. Mention treatments only as published evidence to discuss with a neurologist.
- Keep everything under 450 words. Plain, warm, professional language.
Output: a title and the six sections.`;

export function buildProposalTask(idx: GraphIndex, payload: unknown): TaskResult {
  const p = (payload ?? {}) as { id?: unknown };
  const id = typeof p.id === "string" ? p.id : "";
  const disease = idx.nodeById.get(id);
  if (!disease || disease.type !== "disease") return { error: "Unknown disease.", status: 404 };
  const ctx = diseaseContext(idx, id)!;
  const matches = closestDiseases(idx, id, 4);
  const items = existingWork(idx, id, matches);
  const community = communitiesFor(idx, id);
  const ownOrgs = community.specific;
  const relatedOrgs = [...community.umbrella, ...relatedOrgsFor(idx, matches, [...community.specific, ...community.umbrella])];
  const researchers = researcherPartners(idx, id, matches);
  const gaps = gapsForDisease(idx, ctx);
  const step = suggestNextStep(idx, disease, matches, items, ownOrgs, researchers, gaps);
  const book = new RefBook();

  const best = matches.find((m) => m.sharedMechanisms.length) ?? matches[0];
  // address the proposal to the organisation the suggested next step names, when there is one
  const partnerOrg =
    relatedOrgs.find((o) => step.title.includes(o.org.label)) ??
    (best ? relatedOrgs.find((o) => o.serves.id === best.disease.id) : undefined) ??
    relatedOrgs[0];
  const bridge = researchers.find((r) => r.bridges) ?? researchers[0];
  const partner = partnerOrg
    ? { name: partnerOrg.org.label, kind: "patient organization", serves: partnerOrg.serves.label, refs: book.refsOf([partnerOrg.edge]) }
    : bridge
      ? { name: bridge.researcher.label, kind: "researcher", works_on: bridge.diseases, refs: book.refsOf(bridge.links.map((l) => l.edge)) }
      : best
        ? { name: `the ${best.disease.label} community`, kind: "community without a recorded organization", serves: best.disease.label, refs: [] }
        : null;

  const input = {
    focus_disease: {
      name: disease.label,
      genes: ctx.genes.map((g) => g.label),
      summary: disease.summary ?? null,
      approved_treatment: disease.attrs?.approved_treatment ?? null,
      mechanisms: [...ctx.mechanisms.values()].map((m) => ({ name: m.mechanism.label, refs: book.refsOf([m.edges[m.edges.length - 1]]) })),
    },
    sender: ownOrgs[0]?.org.label ?? `families affected by ${disease.label} (no patient organization specifically for this disease is recorded yet)`,
    partner,
    closest_diseases: matches.slice(0, 3).map((m) => ({
      name: m.disease.label,
      shared_mechanisms: m.sharedMechanisms.map((s) => ({ name: s.mechanism.label, refs: book.refsOf(s.edges.slice(-2)) })),
      shared_symptoms: m.sharedPhenotypes.slice(0, 3).map((s) => ({ name: s.phenotype.label, distinctive: s.distinctive, refs: book.refsOf([s.edges[1]]) })),
      direct_links: book.refsOf(m.directEdges),
      symptoms_not_recorded_there: m.notShared.slice(0, 3).map((n) => n.label),
    })),
    existing_resources: items.slice(0, 8).map((it) => ({
      name: it.node.label,
      type: it.node.type === "asset" && it.node.attrs?.kind ? ASSET_KIND_LABEL[it.node.attrs.kind] : TYPE_LABEL[it.node.type]?.one,
      built_for: it.forDisease.label,
      run_by: it.maintainers.map((m) => m.label),
      reuse: REUSE_META[it.reuse].label,
      reason: it.reason,
      what_differs: it.differs,
      refs: book.refsOf([it.link]),
    })),
    candidate_partners: [
      ...[...ownOrgs, ...relatedOrgs].slice(0, 5).map((o) => ({ name: o.org.label, serves: o.serves.label, refs: book.refsOf([o.edge]) })),
      ...researchers.slice(0, 3).map((r) => ({ name: r.researcher.label, works_on: r.diseases, bridges_diseases: r.bridges, refs: book.refsOf(r.links.map((l) => l.edge)) })),
    ],
    suggested_next_step: { action: step.title, why: step.why, checks: step.checks, refs: book.refsOf(step.edgeIds.map((e) => idx.edgeById.get(e))) },
    open_questions: gaps.map((g) => ({ question: g.question, missing: g.what_is_missing, how_to_find_out: g.how_to_find_out })),
    connections: [] as ReturnType<typeof describeEdge>[],
  };
  input.connections = book.edges.map((e) => describeEdge(idx, e, book.byEdge.get(e.id)!));

  return {
    task: {
      kind: "proposal",
      id,
      instructions: PROPOSAL_INSTRUCTIONS,
      input: JSON.stringify(input, null, 1),
      refs: book.refs,
    },
  };
}

// ---------- compare-questions ----------

const COMPARE_INSTRUCTIONS = `You help two rare-disease patient communities decide whether to join forces. Write the questions an expert (a biochemist, a clinician or a trial designer) should answer first.
Rules:
- Use only the facts in the input JSON. Do not answer the questions, and do not add facts, numbers, names or results.
- Readers are patient-group leaders, not scientists: plain words, one question per sentence, each under 35 words.
- Use these section headings, in this order, and skip a section only if nothing in the input applies: "Biology", "Who can take part", "Measuring progress", "Practical checks".
- Start from the template questions in the input; you may sharpen, merge or add questions that follow from the listed differences.
- Every question must list in edge_ids the refs (like "E3") of the connections it is about. Only a question about a difference with no refs may have an empty list. Never write refs in the text.
- Never give medical or treatment advice.
- At most 10 questions in total.
Output: a short title and the sections.`;

export function buildCompareTask(idx: GraphIndex, payload: unknown): TaskResult {
  const p = (payload ?? {}) as { a?: unknown; b?: unknown };
  const a = typeof p.a === "string" ? p.a : "";
  const b = typeof p.b === "string" ? p.b : "";
  const c = compareDiseases(idx, a, b);
  if (!c) return { error: "Pick two different diseases.", status: 404 };
  const book = new RefBook(60);
  const r = (e: AtlasEdge | undefined) => book.refsOf([e]);
  const input = {
    disease_a: { name: c.a.disease.label, gene: c.shortA },
    disease_b: { name: c.b.disease.label, gene: c.shortB },
    shared_mechanisms: c.shared.map((s) => ({
      name: s.mechanism.label,
      a: { refs: r(s.a.edge), minority_view: s.a.minority, contested: s.a.contested },
      b: { refs: r(s.b.edge), minority_view: s.b.minority, contested: s.b.contested },
    })),
    mechanisms_only_in_a: c.onlyA.map((m) => ({ name: m.link.mechanism.label, minority_view: m.minority, contested: m.contested, refs: r(m.edge) })),
    mechanisms_only_in_b: c.onlyB.map((m) => ({ name: m.link.mechanism.label, minority_view: m.minority, contested: m.contested, refs: r(m.edge) })),
    shared_distinctive_symptoms: c.sharedSymptoms.filter((s) => s.distinctive).slice(0, 6).map((s) => ({ name: s.phenotype.label, refs: book.refsOf([s.edgeA, s.edgeB]) })),
    distinctive_symptoms_only_in_a: c.onlyASymptoms.slice(0, 5).map((s) => ({ name: s.phenotype.label, refs: r(s.edge) })),
    distinctive_symptoms_only_in_b: c.onlyBSymptoms.slice(0, 5).map((s) => ({ name: s.phenotype.label, refs: r(s.edge) })),
    inheritance: c.inheritance,
    onset: c.onset,
    variant_spectrum: {
      a: c.spectrum.a ? { summary: spectrumWords(c.spectrum.a), refs: book.refsOf(c.spectrum.a.edges.slice(0, 3)) } : null,
      b: c.spectrum.b ? { summary: spectrumWords(c.spectrum.b), refs: book.refsOf(c.spectrum.b.edges.slice(0, 3)) } : null,
      differs: c.spectrum.differs,
    },
    resources_covering_both: c.assets.both.map((x) => ({ name: x.node.label, refs: book.refsOf([x.edgeA, x.edgeB]) })),
    resources_only_for_a: c.assets.aOnly.slice(0, 6).map((x) => ({ name: x.node.label, could_serve_b: x.reuse?.reuse ?? "not_applicable", refs: r(x.edgeA) })),
    resources_only_for_b: c.assets.bOnly.slice(0, 6).map((x) => ({ name: x.node.label, could_serve_a: x.reuse?.reuse ?? "not_applicable", refs: r(x.edgeB) })),
    studies_enrolling_both: c.studiesBoth.map((s) => ({
      name: s.node.label,
      eligibility: s.node.type === "study" ? (s.node.attrs?.eligibility_note ?? null) : null,
      refs: book.refsOf([s.edgeA, s.edgeB]),
    })),
    people_and_groups_connected_to_both: c.connectors.slice(0, 8).map((x) => ({ name: x.node.label, kind: x.node.type, refs: book.refsOf([x.linksA[0], x.linksB[0]]) })),
    template_questions: c.questions.map((q) => ({ topic: q.topic, question: q.text, refs: book.refsOf(q.edgeIds.map((id) => idx.edgeById.get(id))) })),
    connections: [] as ReturnType<typeof describeEdge>[],
  };
  input.connections = book.edges.map((e) => describeEdge(idx, e, book.byEdge.get(e.id)!));
  return {
    task: { kind: "compare-questions", id: compareAiId(a, b), instructions: COMPARE_INSTRUCTIONS, input: JSON.stringify(input, null, 1), refs: book.refs },
  };
}

// ---------- experiment (for a computed candidate_for hypothesis) ----------

const EXPERIMENT_INSTRUCTIONS = `You draft a short bench-experiment plan to test one computed hypothesis from a rare-disease knowledge graph. The readers are a patient-group leader and the lab they would approach.
Rules:
- Use only the facts in the input JSON. Do not invent assays, models, reagents, numbers, results, people or funding.
- This tests a hypothesis in cells or animals. Never propose giving the therapy to patients, and never give medical advice.
- Use these section headings, in this order: "What we would test", "Model or assay to use", "What to measure", "Controls", "What result would change the plan", "Caveats".
- Start "What we would test" by saying plainly that this is a hypothesis, not a finding, and name its weakest link.
- Prefer the existing assays and models listed in the input; say when something would need to be built.
- Every sentence that states a fact must list in edge_ids the refs (like "E2") of the connections it relies on. Planning sentences may have an empty list. Never write refs in the text.
- Under 300 words.
Output: a short title and the sections.`;

export function buildExperimentTask(idx: GraphIndex, payload: unknown): TaskResult {
  const p = (payload ?? {}) as { id?: unknown };
  const id = typeof p.id === "string" ? p.id : "";
  const edge = idx.edgeById.get(id);
  if (!edge || edge.type !== "candidate_for") return { error: "Unknown hypothesis.", status: 404 };
  const a = (edge.attrs ?? {}) as {
    title?: string;
    chain?: { kind?: string; edges?: string[] };
    weakest_link?: string;
    caveats?: { kind: string; text: string }[];
    test?: { what_to_test?: string; existing_assay_or_model?: string[]; existing_assay_note?: string; what_result_would_change_the_plan?: string };
  };
  const book = new RefBook(30);
  const hyp = book.ref(edge);
  const chain = (a.chain?.edges ?? []).map((e) => idx.edgeById.get(e)).filter((e): e is AtlasEdge => !!e);
  const input = {
    hypothesis: {
      title: a.title ?? edge.label,
      therapy: idx.nodeById.get(edge.source)?.label,
      disease: idx.nodeById.get(edge.target)?.label,
      confidence: edge.confidence,
      explanation: edge.explanation,
      ref: hyp,
    },
    chain_kind: a.chain?.kind ?? null,
    chain_steps: chain.map((e) => ({ ref: book.ref(e) })),
    weakest_link: a.weakest_link ?? null,
    caveats: a.caveats ?? [],
    test_plan: {
      what_to_test: a.test?.what_to_test ?? null,
      existing_assays_or_models: (a.test?.existing_assay_or_model ?? []).map((x) => idx.nodeById.get(x)?.label ?? x),
      note: a.test?.existing_assay_note ?? null,
      what_result_would_change_the_plan: a.test?.what_result_would_change_the_plan ?? null,
    },
    connections: [] as ReturnType<typeof describeEdge>[],
  };
  input.connections = book.edges.map((e) => describeEdge(idx, e, book.byEdge.get(e.id)!));
  return { task: { kind: "experiment", id, instructions: EXPERIMENT_INSTRUCTIONS, input: JSON.stringify(input, null, 1), refs: book.refs } };
}

// ---------- outreach (a researcher writes to a patient organisation proposing a study) ----------

const OUTREACH_INSTRUCTIONS = `You draft a first message from a researcher to a rare-disease patient organisation, proposing to work together on a study. The reader is the organisation's leadership; the writer is a researcher who has not met them.
Rules:
- Use only the facts in the input JSON. Do not invent study details, sites, funding, numbers, names of people or results. Where something must be filled in by the researcher, write it as [in brackets].
- Never ask the organisation for personal data about patients or families (no names, contacts or records). Ask only whether they would discuss the idea, and how their registry, natural history study or community could take part with proper consent and ethics approval.
- Use these section headings, in this order: "Subject", "Why we are writing", "What we already know", "What we would propose", "What we would ask of you", "Next step".
- "What we already know" names the mechanism, the existing registries, natural history studies or trials, and any limits or contested points in the input.
- Every sentence that states a fact must list in edge_ids the refs (like "E2") of the connections it relies on. Courtesy and planning sentences may have an empty list. Never write refs in the text.
- Warm, plain and respectful. Under 260 words.
Output: a short title and the sections.`;

export function buildOutreachTask(idx: GraphIndex, payload: unknown): TaskResult {
  const p = (payload ?? {}) as { id?: unknown };
  const id = typeof p.id === "string" ? p.id : "";
  const disease = idx.nodeById.get(id);
  if (!disease || disease.type !== "disease") return { error: "Unknown disease.", status: 404 };
  const book = new RefBook(36);
  const nbs = idx.adjacency.get(id) ?? [];
  const pick = (rel: string, dir: "in" | "out", max: number) =>
    nbs
      .filter((n) => n.edge.type === rel && n.dir === dir)
      .sort((a, b) => b.edge.confidence - a.edge.confidence)
      .slice(0, max)
      .map((n) => ({ node: idx.nodeById.get(n.other), edge: n.edge }))
      .filter((x) => x.node);
  const orgs = pick("serves", "in", 6);
  const assets = pick("covers", "in", 8);
  const studies = pick("studies", "in", 8);
  const mechs = pick("driven_by", "out", 5);
  const therapies = pick("developed_for", "in", 5);
  const input = {
    disease: { name: disease.label, summary: disease.summary ?? null },
    patient_organisations: orgs.map((o) => ({ name: o.node!.label, scope: (o.node!.attrs as { scope?: string } | undefined)?.scope ?? null, ref: book.ref(o.edge) })),
    registries_studies_and_resources: assets.map((a) => ({ name: a.node!.label, kind: (a.node!.attrs as { kind?: string } | undefined)?.kind ?? null, ref: book.ref(a.edge) })),
    clinical_studies: studies.map((s) => {
      const at = (s.node!.attrs ?? {}) as { status?: string; phase?: string; study_type?: string };
      return { title: s.node!.label, status: at.status ?? null, phase: at.phase ?? null, type: at.study_type ?? null, ref: book.ref(s.edge) };
    }),
    mechanisms: mechs.map((m) => ({ name: m.node!.label, ref: book.ref(m.edge) })),
    therapies_in_development: therapies.map((t) => ({ name: t.node!.label, ref: book.ref(t.edge) })),
    connections: [] as ReturnType<typeof describeEdge>[],
  };
  input.connections = book.edges.map((e) => describeEdge(idx, e, book.byEdge.get(e.id)!));
  return { task: { kind: "outreach", id, instructions: OUTREACH_INSTRUCTIONS, input: JSON.stringify(input, null, 1), refs: book.refs } };
}

export function buildTask(idx: GraphIndex, kind: string, payload: unknown): TaskResult {
  if (kind === "outreach") return buildOutreachTask(idx, payload);
  if (kind === "experiment") return buildExperimentTask(idx, payload);
  if (kind === "explain-path") return buildExplainPathTask(idx, payload);
  if (kind === "proposal") return buildProposalTask(idx, payload);
  if (kind === "compare-questions") return buildCompareTask(idx, payload);
  return { error: `Unknown kind: ${kind}`, status: 400 };
}

// ---------- output validation ----------

const str = (v: unknown, max: number) => (typeof v === "string" ? v.trim().slice(0, max) : "");
const arr = (v: unknown) => (Array.isArray(v) ? v : []);

/**
 * Keeps only citations that point at connections in this task's payload (by ref "E3" or by exact
 * edge id). Sentences whose citations all drop are kept with edge_ids [] (rendered as AI framing).
 */
export function sanitizeDoc(raw: unknown, refs: Map<string, string>): { doc: AiDoc; dropped: number } {
  const allowed = new Set(refs.values());
  const r = (raw ?? {}) as { title?: unknown; sections?: unknown };
  let dropped = 0;
  const sections = arr(r.sections)
    .slice(0, 8)
    .map((s) => {
      const sec = (s ?? {}) as { heading?: unknown; sentences?: unknown };
      return {
        heading: str(sec.heading, 140),
        sentences: arr(sec.sentences)
          .slice(0, 40)
          .map((x) => {
            const sent = (x ?? {}) as { text?: unknown; edge_ids?: unknown };
            const ids: string[] = [];
            for (const c of arr(sent.edge_ids)) {
              const key = String(c).trim().replace(/^\[|\]$/g, "");
              const id = refs.get(key.toUpperCase()) ?? (allowed.has(key) ? key : undefined);
              if (id) {
                if (!ids.includes(id)) ids.push(id);
              } else dropped++;
            }
            return { text: str(sent.text, 1500), edge_ids: ids };
          })
          .filter((x) => x.text),
      };
    })
    .filter((s) => s.heading || s.sentences.length);
  return { doc: { title: str(r.title, 200) || "Untitled", sections }, dropped };
}
