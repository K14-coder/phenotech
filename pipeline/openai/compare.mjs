/**
 * Step 4: compare an independent reading (READER=openai or claude) with the curated graph.
 *
 *   node pipeline/openai/compare.mjs     # no model calls
 *
 * Each verified, reconciled claim is turned into graph assertions (source, type, target, polarity)
 * by fixed, documented rules (see canonical()). Then, per graph edge:
 *   a) edge exists and the PMID is already in its evidence/counter_evidence -> agreement record
 *      (agrees = the claim's polarity matches how the curators filed that PMID on that edge)
 *   b) edge exists, PMID not on it, claim supports it  -> new supporting source
 *   c) no edge, both endpoints exist, claim positive   -> candidate new edge (fragment)
 *   d) edge exists, PMID not on it, claim contradicts it (negated, or the opposite effect class for
 *      the same gene)                                     -> contradiction flagged for human review
 * One record per (edge, PMID). Outputs:
 *   data/build/crosscheck.json            (a, b, d; applied by pipeline/build_graph.py)
 *   data/curated/<reader>_extracted.json    (c as unverified edges, plus synonym stubs)
 *   data/raw/<reader>/compare_details.json  (every assertion and decision, for audit)
 *   docs/agent-reports/<reader>-extraction.md
 * (READER=openai keeps the original names: data/build/crosscheck.json, openai_extracted.json.)
 */
import path from 'node:path';
import { existsSync } from 'node:fs';
import {
  READER, READER_LABEL,
  CANDIDATES, CROSSCHECK, FRAGMENT, OUT_RAW, RUN_STATE, loadAllAbstracts, loadBaselineGraph, readJson, readUsageLog, today, writeJson,
} from './common.mjs';
import { writeReport } from './report.mjs';

export const EFFECT_CLASS = {
  'mech:loss-of-function': 'decrease',
  'mech:haploinsufficiency': 'decrease',
  'mech:protein-destabilization': 'decrease',
  'mech:dominant-negative': 'decrease',
  'mech:gain-of-function': 'increase',
};
const SYMMETRIC = new Set(['shares_mechanism', 'similar_phenotype']);
const LEVEL = { clinical_trial: 'clinical', functional_study: 'experimental', animal_model: 'experimental', case_report: 'observational', case_series: 'observational', cohort: 'observational', review: 'observational' };
const CERT_RANK = { established: 3, suggested: 2, speculative: 1 };
const CONFIDENCE = { established: 0.5, suggested: 0.45, speculative: 0.35 }; // capped at 0.5 by design
const LABELS = { causes: 'causes', has_effect: 'has effect', participates_in: 'takes part in', driven_by: 'driven by', has_phenotype: 'has feature', targets: 'targets', developed_for: 'developed for' };
const STUDY_WORDS = { clinical_trial: 'clinical trial', case_report: 'case report', case_series: 'case series', cohort: 'cohort study', functional_study: 'functional study', animal_model: 'animal-model study', review: 'review' };
const TIER = { direct: 0, lifted: 0, implied: 1, opposite_effect: 2 };

function main() {
  const graph = loadBaselineGraph(); // graph.json minus this layer's own earlier contributions
  const nodes = new Map(graph.nodes.map((n) => [n.id, n]));
  const edgeById = new Map(graph.edges.map((e) => [e.id, e]));
  const bySourceType = new Map();
  for (const e of graph.edges) {
    const k = `${e.source}|${e.type}`;
    if (!bySourceType.has(k)) bySourceType.set(k, []);
    bySourceType.get(k).push(e);
  }
  const rec = readJson(path.join(OUT_RAW, 'claims_reconciled.json'));
  const verifiedFile = readJson(path.join(OUT_RAW, 'claims_verified.json'));
  const abstracts = loadAllAbstracts();
  const models = verifiedFile.models;
  const model = models.length === 1 ? models[0] : models.join('+');
  const by = `${READER}:${model}`;

  const geneOf = (id) => {
    if (!id) return null;
    if (id.startsWith('gene_level:')) return id.slice(11);
    if (id.startsWith('gene:')) return id.slice(5);
    if (id.startsWith('disease:')) return id.slice(8);
    if (id.startsWith('vg:')) return id.split(':')[1];
    return null;
  };
  const kindOf = (id) => (id?.startsWith('gene_level:') ? 'gene_level' : nodes.get(id)?.type);
  const diseaseOf = (id) => (nodes.has(`disease:${geneOf(id)}`) ? `disease:${geneOf(id)}` : null);
  const geneNode = (id) => (nodes.has(`gene:${geneOf(id)}`) ? `gene:${geneOf(id)}` : null);
  const GENEISH = ['gene', 'variant_group', 'gene_level'];

  /** Fixed rules from a claim to graph assertions. Returns { assertions } or { drop: reason }. */
  function canonical(c) {
    const S = c.subject_node;
    const O = c.object_node;
    const st = kindOf(S);
    const ot = kindOf(O);
    const out = [];
    switch (c.relation) {
      case 'causes':
        if (!GENEISH.includes(st) || ot !== 'disease') return { drop: 'endpoint types do not fit the relation' };
        if (geneOf(S) !== geneOf(O)) return { drop: 'gene and gene-defined disease differ' };
        out.push({ s: geneNode(S), t: 'causes', o: O, via: st === 'gene' ? 'direct' : 'lifted' });
        break;
      case 'has_effect':
      case 'driven_by':
      case 'participates_in': {
        if (ot !== 'mechanism') return { drop: 'endpoint types do not fit the relation' };
        const mk = nodes.get(O)?.attrs?.kind;
        // By curation design, multi-gene deletions carry no mechanism edge (the segment removes several genes).
        if (String(S).endsWith(':contiguous-gene-deletion')) return { drop: 'multi-gene deletion: no mechanism edge by design' };
        if (c.relation === 'participates_in' && mk === 'process' && GENEISH.includes(st)) {
          out.push({ s: geneNode(S), t: 'participates_in', o: O, via: st === 'gene' ? 'direct' : 'lifted' });
        } else if (st === 'variant_group' && mk === 'effect') {
          out.push({ s: S, t: 'has_effect', o: O, via: c.relation === 'has_effect' ? 'direct' : 'lifted' });
          out.push({ s: diseaseOf(S), t: 'driven_by', o: O, via: 'implied' }); // curators mirror vg effects onto the disease
        } else if ([...GENEISH, 'disease'].includes(st)) {
          out.push({ s: diseaseOf(S), t: 'driven_by', o: O, via: c.relation === 'driven_by' && st === 'disease' ? 'direct' : 'lifted' });
        } else return { drop: 'endpoint types do not fit the relation' };
        break;
      }
      case 'has_phenotype':
        if (ot !== 'phenotype' || ![...GENEISH, 'disease'].includes(st)) return { drop: 'endpoint types do not fit the relation' };
        if (c.species && c.species !== 'human') return { drop: 'phenotype seen in a model, not in patients' };
        out.push({ s: diseaseOf(S), t: 'has_phenotype', o: O, via: st === 'disease' ? 'direct' : 'lifted' });
        break;
      case 'targets':
        if (st !== 'therapy' || ot !== 'mechanism') return { drop: 'endpoint types do not fit the relation' };
        out.push({ s: S, t: 'targets', o: O, via: 'direct' });
        break;
      case 'developed_for':
        if (st !== 'therapy' || ![...GENEISH, 'disease'].includes(ot)) return { drop: 'endpoint types do not fit the relation' };
        out.push({ s: S, t: 'developed_for', o: diseaseOf(O), via: ot === 'disease' ? 'direct' : 'lifted' });
        break;
      default:
        return { drop: 'relation not compared' };
    }
    const pol = c.negated ? -1 : 1;
    return { assertions: out.filter((a) => a.s && a.o).map((a) => ({ ...a, pol })) };
  }

  const findEdge = (s, t, o) => edgeById.get(`${s}|${t}|${o}`) ?? (SYMMETRIC.has(t) ? edgeById.get(`${o}|${t}|${s}`) : undefined);
  const curatedPolarity = (edge, pmid) => {
    const P = new Set();
    for (const ev of edge.evidence ?? []) if (ev.ref === `PMID:${pmid}`) P.add(ev.supports === false ? -1 : 1);
    for (const ev of edge.counter_evidence ?? []) if (ev.ref === `PMID:${pmid}`) P.add(-1);
    return P;
  };

  // ---- 1. claims -> assertions on existing edges, or candidate edges
  const claimStats = { verified: 0, reconciled: 0, compared: 0, dropped: {} };
  const onEdge = new Map(); // `${edgeId}|${pmid}` -> [{claim, pol, via}]
  const candidates = new Map(); // edgeId -> {s,t,o, claims: []}
  const negativeNoEdge = [];
  for (const c of rec.claims) {
    claimStats.verified += 1;
    if (!c.subject_node || !c.object_node) continue;
    claimStats.reconciled += 1;
    const { assertions, drop } = canonical(c);
    if (drop) {
      claimStats.dropped[drop] = (claimStats.dropped[drop] ?? 0) + 1;
      continue;
    }
    claimStats.compared += 1;
    const push = (edge, pol, via) => {
      const k = `${edge.id}|${c.pmid}`;
      if (!onEdge.has(k)) onEdge.set(k, []);
      onEdge.get(k).push({ claim: c, pol, via });
    };
    for (const a of assertions) {
      const edge = findEdge(a.s, a.t, a.o);
      if (edge) push(edge, a.pol, a.via);
      else if (a.via !== 'implied') {
        if (a.pol > 0) {
          const id = `${a.s}|${a.t}|${a.o}`;
          if (!candidates.has(id)) candidates.set(id, { s: a.s, t: a.t, o: a.o, claims: [] });
          candidates.get(id).claims.push(c);
        } else negativeNoEdge.push({ edge_id: `${a.s}|${a.t}|${a.o}`, claim: c });
      }
      // (d) opposite effect class for the same gene (gain of function vs loss of function /
      // haploinsufficiency / dominant-negative / destabilization). Flag only where the graph has no edge
      // of the claimed class from this source (otherwise the curators already show both sides), or
      // where the curators cite this same paper on the opposite edge.
      if (a.pol > 0 && EFFECT_CLASS[a.o] && (a.t === 'has_effect' || a.t === 'driven_by')) {
        const siblings = bySourceType.get(`${a.s}|${a.t}`) ?? [];
        const classRepresented = siblings.some((e) => EFFECT_CLASS[e.target] === EFFECT_CLASS[a.o]);
        for (const other of siblings) {
          const cls = EFFECT_CLASS[other.target];
          if (!cls || cls === EFFECT_CLASS[a.o]) continue;
          if (!classRepresented || curatedPolarity(other, c.pmid).size) push(other, -1, 'opposite_effect');
        }
      }
    }
  }

  // ---- 2. one decision per (edge, PMID)
  const best = (list) => [...list].sort((x, y) => (CERT_RANK[y.claim.certainty] ?? 0) - (CERT_RANK[x.claim.certainty] ?? 0) || TIER[x.via] - TIER[y.via])[0];
  const decisions = [];
  for (const [key, list] of onEdge) {
    const pmid = key.slice(key.lastIndexOf('|') + 1);
    const edgeId = key.slice(0, key.lastIndexOf('|'));
    const edge = edgeById.get(edgeId);
    const tier = Math.min(...list.map((x) => TIER[x.via]));
    const top = list.filter((x) => TIER[x.via] === tier);
    const mixed = new Set(top.map((x) => x.pol)).size > 1;
    const P = curatedPolarity(edge, pmid);
    let d;
    if (P.size) {
      const agreeing = top.filter((x) => P.has(x.pol));
      const pick = agreeing.length ? best(agreeing) : best(top);
      d = { case: 'a', agrees: agreeing.length > 0, pick, curated_polarity: [...P] };
    } else if (top.some((x) => x.pol > 0)) {
      d = { case: 'b', agrees: true, pick: best(top.filter((x) => x.pol > 0)) };
    } else {
      d = { case: 'd', agrees: false, pick: best(top) };
    }
    decisions.push({ edge_id: edgeId, edge_type: edge.type, pmid, ...d, mixed, n_claims: list.length, tier });
  }

  // ---- 3. crosscheck.json
  const ref = (pmid) => abstracts.get(pmid);
  const edgesOut = {};
  for (const d of decisions.sort((x, y) => x.edge_id.localeCompare(y.edge_id) || x.pmid.localeCompare(y.pmid))) {
    const c = d.pick.claim;
    const r = ref(d.pmid);
    (edgesOut[d.edge_id] ??= []).push({
      ref: `PMID:${d.pmid}`, agrees: d.agrees, quote: c.quote, url: `https://pubmed.ncbi.nlm.nih.gov/${d.pmid}/`,
      title: r?.title ?? c.title, year: r?.year ?? c.year ?? null, study_type: c.study_type, certainty: c.certainty,
      case: d.case, via: d.pick.via, negated: c.negated, species: c.species ?? null, claim_id: c.claim_id,
      ...(d.mixed ? { mixed: true } : {}),
    });
  }
  const crosscheck = { model, generated_at: new Date().toISOString(), extracted_by: by, edges: edgesOut };
  writeJson(CROSSCHECK, crosscheck);

  // ---- 4. fragment: candidate edges (c) + synonym stubs
  const fragEdges = [];
  for (const [id, cand] of [...candidates].sort(([a], [b]) => a.localeCompare(b))) {
    const perPmid = new Map();
    for (const c of cand.claims) {
      const prev = perPmid.get(c.pmid);
      if (!prev || (CERT_RANK[c.certainty] ?? 0) > (CERT_RANK[prev.certainty] ?? 0)) perPmid.set(c.pmid, c);
    }
    const picks = [...perPmid.values()].sort((a, b) => a.pmid.localeCompare(b.pmid));
    const levels = picks.map((c) => LEVEL[c.study_type] ?? 'observational');
    const rank = { clinical: 3, experimental: 2, observational: 1 };
    const level = levels.sort((a, b) => rank[b] - rank[a])[0];
    const topCert = picks.map((c) => c.certainty).sort((a, b) => CERT_RANK[b] - CERT_RANK[a])[0];
    const confidence = Math.min(0.5, CONFIDENCE[topCert] ?? 0.35);
    const label = (nid) => nodes.get(nid)?.label ?? nid;
    const verb = { established: 'reports', suggested: 'suggests', speculative: 'proposes' }[topCert] ?? 'reports';
    const who = picks.length === 1
      ? `A ${picks[0].year ?? ''} ${STUDY_WORDS[picks[0].study_type] ?? 'paper'} (PMID:${picks[0].pmid})`.replace('A  ', 'A ')
      : `${picks.length} papers (${picks.map((c) => `PMID:${c.pmid}`).join(', ')})`;
    const vgPhrase = (vg) => `${geneOf(vg)} ${(label(vg).split(':')[1] ?? '').split('(')[0].trim().toLowerCase()}`;
    const what = {
      causes: `changes in ${label(cand.s)} cause ${label(cand.o)}`,
      has_effect: `${vgPhrase(cand.s)} lead to ${label(cand.o).toLowerCase()}`,
      participates_in: `the ${geneOf(cand.s)} protein takes part in ${label(cand.o).toLowerCase()}`,
      driven_by: `${label(cand.s)} involve ${label(cand.o).toLowerCase()}`,
      has_phenotype: `${label(cand.o).toLowerCase()} is seen in people with ${label(cand.s)}`,
      targets: `${label(cand.s)} acts on ${label(cand.o).toLowerCase()}`,
      developed_for: `${label(cand.s)} was developed, tested or used for ${label(cand.o)}`,
    }[cand.t];
    const ns = picks.map((c) => c.species).filter(Boolean);
    fragEdges.push({
      id, source: cand.s, target: cand.o, type: cand.t, label: LABELS[cand.t],
      explanation: `${who} ${verb} that ${what}. ${READER === 'openai' ? 'Found by automated extraction with OpenAI' : `Found by an independent ${READER_LABEL} reading`}; not yet reviewed by a person.`,
      evidence_level: level,
      status: 'unverified',
      confidence,
      evidence: picks.map((c) => ({
        source: 'PubMed', ref: `PMID:${c.pmid}`, url: `https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`,
        title: ref(c.pmid)?.title ?? c.title, year: ref(c.pmid)?.year ?? c.year ?? undefined, quote: c.quote,
        kind: 'publication', study_type: c.study_type, supports: true, extracted_by: `${READER}:${c.model}`,
        verified: true, retrieved: today(),
      })),
      attrs: {
        extraction: READER, needs_review: true, certainty: topCert,
        species: [...new Set(ns)], claim_ids: cand.claims.map((c) => c.claim_id),
      },
    });
  }
  const stubs = new Map();
  for (const p of rec.synonym_proposals) {
    const n = nodes.get(p.node_id);
    if (!n) continue;
    if (!stubs.has(n.id)) stubs.set(n.id, { id: n.id, type: n.type, label: n.label, synonyms: [] });
    if (!stubs.get(n.id).synonyms.includes(p.synonym)) stubs.get(n.id).synonyms.push(p.synonym);
  }
  // READER=openai merges its candidate edges as unverified (the original behaviour). Other readers' candidate
  // edges wait in data/build/<reader>_candidate_edges.json until a person reviews them: unreviewed AI edges in
  // the graph would also become test cases and features of the therapy-transfer benchmark.
  const mergeCandidates = READER === 'openai';
  const fragment = { nodes: [...stubs.values()].sort((a, b) => a.id.localeCompare(b.id)), edges: mergeCandidates ? fragEdges : [], clusters: [], gaps: [] };
  writeJson(FRAGMENT, fragment);
  if (!mergeCandidates) {
    writeJson(CANDIDATES, { generated_at: new Date().toISOString(), reader: READER, note: 'Not merged into the graph. Review, then move accepted edges into a curated fragment.', edges: fragEdges });
  }

  // ---- 5. audit file + report
  const curatedPairs = [];
  const processed = new Set(Object.keys(verifiedFile.per_pmid));
  const COMPARED_TYPES = new Set(['causes', 'has_effect', 'participates_in', 'driven_by', 'has_phenotype', 'targets', 'developed_for']);
  for (const e of graph.edges) {
    if (!COMPARED_TYPES.has(e.type)) continue;
    const seen = new Set();
    for (const ev of [...(e.evidence ?? []), ...(e.counter_evidence ?? [])]) {
      const pmid = String(ev.ref ?? '').startsWith('PMID:') ? ev.ref.slice(5) : null;
      if (!pmid || !processed.has(pmid) || seen.has(pmid)) continue;
      seen.add(pmid);
      curatedPairs.push({ edge_id: e.id, edge_type: e.type, pmid, source: ev.source });
    }
  }
  const details = {
    generated_at: new Date().toISOString(), model, claim_stats: claimStats,
    decisions: decisions.map((d) => ({ ...d, pick: { via: d.pick.via, pol: d.pick.pol, claim_id: d.pick.claim.claim_id, quote: d.pick.claim.quote } })),
    candidates: fragEdges.map((e) => e.id),
    negative_no_edge: negativeNoEdge.map((x) => ({ edge_id: x.edge_id, claim_id: x.claim.claim_id, quote: x.claim.quote })),
    curated_pairs_for_processed_pmids: curatedPairs,
  };
  writeJson(path.join(OUT_RAW, 'compare_details.json'), details);

  writeReport({
    graph, nodes, edgeById, abstracts, model, verifiedFile, rec, claimStats, decisions, fragEdges, fragment,
    negativeNoEdge, curatedPairs, usage: readUsageLog(), runState: existsSync(RUN_STATE) ? readJson(RUN_STATE) : {},
  });

  const count = (k) => decisions.filter((d) => d.case === k).length;
  const a = decisions.filter((d) => d.case === 'a');
  console.log(`[compare] claims: ${JSON.stringify(claimStats)}`);
  console.log(`[compare] (a) ${count('a')} cited pairs, agree ${a.filter((d) => d.agrees).length}; (b) ${count('b')} new supporting; (c) ${fragEdges.length} candidate edges; (d) ${count('d')} contradictions`);
  console.log(`[compare] synonym stubs: ${fragment.nodes.length} nodes, ${fragment.nodes.reduce((s, n) => s + n.synonyms.length, 0)} synonyms`);
}

main();
