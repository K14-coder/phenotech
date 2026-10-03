/** Writes docs/agent-reports/openai-extraction.md from the compare.mjs results. */
import { writeFileSync } from 'node:fs';
import { REPORT } from './common.mjs';

const pct = (a, b) => (b ? `${((100 * a) / b).toFixed(1)}%` : 'n/a');
const esc = (s) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');
const CERT_RANK = { established: 3, suggested: 2, speculative: 1 };
const TYPE_WEIGHT = { driven_by: 2, has_effect: 2, targets: 2, developed_for: 2, causes: 2, participates_in: 1, has_phenotype: 0.5 };

const squash = (s) => String(s ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase();

/** Both extractors quote the same sentence: the difference is how a limiting/mixed finding is filed. */
export function sameSentence(d, edge) {
  const q = squash(d.pick.claim.quote);
  return [...(edge.evidence ?? []), ...(edge.counter_evidence ?? [])]
    .some((ev) => ev.ref === `PMID:${d.pmid}` && ev.quote && (squash(ev.quote).includes(q) || q.includes(squash(ev.quote))));
}

export function priority(d, edge) {
  return (d.case === 'a' ? 3 : 0) + (d.pick.via === 'opposite_effect' ? 0 : 1) + (edge?.confidence ?? 0)
    + (CERT_RANK[d.pick.claim.certainty] ?? 0) / 3 + (TYPE_WEIGHT[d.edge_type] ?? 1)
    - (sameSentence(d, edge) ? 2 : 0);
}

function curatedQuotes(edge, pmid) {
  const items = [...(edge.evidence ?? []).map((ev) => ({ ...ev, side: ev.supports === false ? 'contradicts' : 'supports' })),
    ...(edge.counter_evidence ?? []).map((ev) => ({ ...ev, side: 'contradicts' }))];
  const same = items.filter((ev) => ev.ref === `PMID:${pmid}`);
  if (same.length) return same;
  // Not cited on this edge: show the curators' main supporting evidence instead (quoted items first).
  const supporting = items.filter((ev) => ev.side === 'supports');
  const quoted = supporting.filter((ev) => ev.quote);
  return (quoted.length ? quoted : supporting).slice(0, 2);
}

export function writeReport(ctx) {
  const { edgeById, model, verifiedFile, rec, claimStats, decisions, fragEdges, fragment, negativeNoEdge, curatedPairs, usage, runState, abstracts } = ctx;
  const vs = verifiedFile.stats;
  const allBio = [...abstracts.values()].filter((r) => r.set === 'biology').length;
  const allCom = [...abstracts.values()].filter((r) => r.set === 'community').length;
  const a = decisions.filter((d) => d.case === 'a');
  const aAgree = a.filter((d) => d.agrees);
  const b = decisions.filter((d) => d.case === 'b');
  const dd = decisions.filter((d) => d.case === 'd');
  const disagreements = [...a.filter((d) => !d.agrees), ...dd]
    .map((d) => ({ d, edge: edgeById.get(d.edge_id) }))
    .sort((x, y) => priority(y.d, y.edge) - priority(x.d, x.edge) || x.d.edge_id.localeCompare(y.d.edge_id));
  const reFound = new Set(a.map((d) => `${d.edge_id}|${d.pmid}`));
  const types = [...new Set([...curatedPairs.map((p) => p.edge_type), ...decisions.map((d) => d.edge_type)])].sort();
  const ok = usage.filter((u) => u.ok);
  const tok = (u, k) => Number(u.usage?.[k] ?? 0);
  const sum = (list, k) => list.reduce((s, u) => s + tok(u, k), 0);
  const reasoning = (list) => list.reduce((s, u) => s + Number(u.usage?.output_tokens_details?.reasoning_tokens ?? 0), 0);
  const failures = usage.filter((u) => !u.ok);
  const scripts = ['extract', 'reconcile'];
  const stops = Object.entries(runState).filter(([, v]) => v?.stopped).map(([k, v]) => `${k}: ${v.stopped.kind} (${v.stopped.message})`);
  const ms = (list) => list.reduce((s, u) => s + Number(u.ms ?? 0), 0);
  const mention = rec.stats.mentions;
  const synCount = fragment.nodes.reduce((s, n) => s + n.synonyms.length, 0);
  const L = [];
  const p = (...lines) => L.push(...lines);

  p('# OpenAI extraction: an independent second reading of the literature',
    '',
    `Generated ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC by \`pipeline/openai/\`. Model: **\`${model}\`** (as returned by the API), via Sign in with ChatGPT (plan usage), structured outputs (\`json_schema\`, strict). Nothing here was typed by hand: every number below is recomputed by \`node pipeline/openai/compare.mjs\`.`,
    '',
    'The curated graph was built by agent curation with string-verified quotes. This layer reads the same stored abstracts **independently** with OpenAI, keeps only claims whose quote is a verbatim sentence of the stored abstract, maps them onto graph nodes, and compares. The evidence story becomes: **two independent extractors, verbatim quotes, disagreements flagged for human review.**',
    '',
    '## Headline numbers',
    '',
    `| | |`,
    `|---|---|`,
    `| Abstracts processed | **${vs.abstracts_with_extraction}** (biology ${vs.by_set.biology.abstracts}/${allBio}; community ${vs.by_set.community.abstracts}/${allCom} with abstracts) |`,
    `| Claims extracted | ${vs.claims} |`,
    `| Quote-verified (verbatim substring of stored title + abstract) | **${vs.verified} (${vs.verified_pct}%)**; ${vs.rejected} rejected, none edited${vs.verified_but_multi_sentence ? ` (${vs.verified_but_multi_sentence} verified quotes span more than one sentence)` : ''} |`,
    `| Reconciled (both endpoints mapped to an existing node) | ${claimStats.reconciled} (${pct(claimStats.reconciled, claimStats.verified)} of verified) |`,
    `| Compared with graph edges (after the fixed mapping rules) | ${claimStats.compared} |`,
    `| **Agreement** on (edge, PMID) pairs both extractors cite | **${aAgree.length}/${a.length} (${pct(aAgree.length, a.length)})** |`,
    `| Curated (edge, PMID) pairs for these abstracts re-found independently | ${reFound.size}/${curatedPairs.length} (${pct(reFound.size, curatedPairs.length)}) |`,
    `| (a) disagreements on a paper both cite | ${a.length - aAgree.length} |`,
    `| (b) new supporting sources for existing edges | ${b.length} |`,
    `| (d) new contradicting sources, flagged for review | ${dd.length} |`,
    `| (c) candidate new edges (\`status: unverified\`, confidence ≤ 0.5) | ${fragEdges.length} |`,
    `| Synonyms proposed | ${synCount} on ${fragment.nodes.length} nodes |`,
    ...(() => {
      const left = rec.claims.flatMap((c) => ['subject', 'object'].filter((s) => c[`${s}_resolution`] === 'unresolved(no-llm-answer)').map(() => c.pmid));
      return left.length
        ? [`| Usage limit | The ChatGPT plan limit was reached during reconciliation: ${new Set(left).size} abstracts (${rec.stats.methods['unresolved(no-llm-answer)'] ?? 0} mentions) got the deterministic index only. Rerunning \`reconcile.mjs\` later completes them from cache. |`]
        : [];
    })(),
    '');

  p('## Agreement by relation type', '',
    'A pair is one graph edge and one PMID. "Agree" means the OpenAI claim has the same polarity as the curators\' filing of that PMID on that edge (supporting evidence vs. counter-evidence). Coverage is how many curated pairs for the processed abstracts the model found on its own.',
    '',
    '| Edge type | Pairs both cite | Agree | Disagree | Agreement | Curated pairs re-found | New supporting (b) | New contradicting (d) |',
    '|---|---|---|---|---|---|---|---|');
  for (const t of types) {
    const at = a.filter((d) => d.edge_type === t);
    const ag = at.filter((d) => d.agrees).length;
    const cp = curatedPairs.filter((x) => x.edge_type === t);
    const rf = cp.filter((x) => reFound.has(`${x.edge_id}|${x.pmid}`)).length;
    p(`| \`${t}\` | ${at.length} | ${ag} | ${at.length - ag} | ${pct(ag, at.length)} | ${rf}/${cp.length} | ${b.filter((d) => d.edge_type === t).length} | ${dd.filter((d) => d.edge_type === t).length} |`);
  }
  p(`| **all** | **${a.length}** | **${aAgree.length}** | **${a.length - aAgree.length}** | **${pct(aAgree.length, a.length)}** | **${reFound.size}/${curatedPairs.length}** | **${b.length}** | **${dd.length}** |`, '',
    'Note: `has_phenotype` pairs come from HPO annotations that cite a PMID (no curator quote); the model reads only the abstract, so phenotypes reported in full texts are not expected to be re-found.',
    '');

  p('## Disagreements for a biochemist to review', '',
    `${disagreements.length} items, most important first (a paper both extractors cite but read differently ranks highest; then direct contradictions on high-confidence mechanism and therapy edges). "Curated" is the quote the curators filed for that PMID on the edge, or, when the curators did not cite this PMID, their main supporting quote. In the graph these appear as \`cross_checked.agrees: false\` stamps (a) or as counter-evidence with \`needs_review: true\` (d); they do not change an edge's status until a person reviews them.`,
    '');
  disagreements.slice(0, 40).forEach(({ d, edge }, i) => {
    const c = d.pick.claim;
    const modelReading = d.pick.pol > 0
      ? 'takes it as **supporting** the edge'
      : c.negated ? 'says the relation does **not** hold' : 'reports the **opposite effect class** for this gene';
    const same = sameSentence(d, edge);
    const why = d.case === 'a'
      ? `Both cite PMID:${d.pmid}. Curators filed it as **${d.curated_polarity.includes(1) ? 'supporting' : 'contradicting'}**; the OpenAI reading ${modelReading}.${same ? ' **Same sentence, filed differently:** both extractors quote it; the curators treat it as a limiting or mixed finding (counter-evidence), the model as plain support. A reviewer decides which filing fits.' : ''}`
      : d.pick.via === 'opposite_effect'
        ? `New source: the OpenAI reading of PMID:${d.pmid} reports the **opposite effect class** for this gene, and the graph has no edge for that effect.`
        : `New source: the OpenAI reading of PMID:${d.pmid} states the relation does **not** hold (negated).`;
    p(`### ${i + 1}. \`${d.edge_id}\``, '',
      `${why} Edge: ${edge.status}, confidence ${edge.confidence}, ${edge.evidence_level}. Claim: ${c.subject_mention} → *${c.relation}* → ${c.object_mention} (${c.certainty}, ${c.study_type}${c.species ? `, ${c.species}` : ''}${c.negated ? ', negated' : ''}${d.mixed ? '; the same paper also yields the opposite reading' : ''}).`,
      '');
    for (const ev of curatedQuotes(edge, d.pmid)) {
      p(`- Curated (${ev.ref}, ${ev.side}): "${esc(ev.quote ?? `(no quote: ${ev.source} record)`)}"`);
    }
    p(`- OpenAI (PMID:${d.pmid}${d.pick.via === 'opposite_effect' ? ', opposite effect' : ''}): "${esc(c.quote)}"`, '');
  });
  if (disagreements.length > 40) p(`…and ${disagreements.length - 40} more in \`data/build/crosscheck.json\` (items with \`agrees: false\`).`, '');

  p('## New supporting sources for existing edges (b)', '',
    `${b.length} (edge, PMID) pairs where the model found support for an existing edge in a paper the curators did not cite on that edge. \`build_graph.py\` adds them as evidence with \`extracted_by: openai:${model}\`, \`verified: true\`.`, '',
    '| Edge type | New supporting sources |', '|---|---|',
    ...[...new Set(b.map((d) => d.edge_type))].sort().map((t) => `| \`${t}\` | ${b.filter((d) => d.edge_type === t).length} |`), '');
  const bTop = [...b].sort((x, y) => (y.edge_type === 'has_phenotype' ? 0 : 1) - (x.edge_type === 'has_phenotype' ? 0 : 1) || x.edge_id.localeCompare(y.edge_id)).slice(0, 25);
  for (const d of bTop) p(`- \`${d.edge_id}\` ← PMID:${d.pmid} (${d.pick.claim.certainty}, ${d.pick.claim.study_type}): "${esc(d.pick.claim.quote)}"`);
  if (b.length > 25) p(`- …${b.length - 25} more in \`data/build/crosscheck.json\` (\`case: "b"\`).`);
  p('');

  p('## Candidate new edges (c)', '',
    `${fragEdges.length} edges whose endpoints both exist but which the graph lacks. Written to \`data/curated/openai_extracted.json\` with \`status: "unverified"\`, confidence ≤ 0.5, evidence level from the study type (trial → clinical; functional/animal → experimental; case report/series/cohort/review → observational) and a verbatim, string-verified quote per PMID.`, '',
    '| Candidate edge | PMIDs | Level | Confidence | Certainty |', '|---|---|---|---|---|',
    ...fragEdges.map((e) => `| \`${e.id}\` | ${e.evidence.map((ev) => ev.ref.slice(5)).join(', ')} | ${e.evidence_level} | ${e.confidence} | ${e.attrs.certainty} |`), '');

  p('## Synonyms added', '',
    `${synCount} names on ${fragment.nodes.length} nodes. A synonym is proposed only when the OpenAI reconciliation step judged the mention to be **another name for exactly that node** ("same", not a narrower or descriptive mention), the id came from the mention's candidate list, and the mention appears literally in the abstract. They are node stubs (id, type, label, synonyms) that the merge step unions.`, '',
    '| Node | Synonym | PMID(s) | Model\'s justification |', '|---|---|---|---|',
    ...rec.synonym_proposals.map((s) => `| \`${s.node_id}\` (${esc(s.node_label)}) | ${esc(s.synonym)} | ${s.pmids.join(', ')} | ${esc(s.justification)} |`), '',
    (rec.synonym_rejected ?? []).length
      ? `Not proposed despite a "same" judgement (hygiene rules in \`reconcile.mjs\`): ${rec.synonym_rejected.map((x) => `"${esc(x.mention)}" → \`${x.node_id}\` (${x.why})`).join('; ')}.`
      : '', '');

  p('## Reconciliation', '',
    `${mention.total} distinct mentions (per abstract and type): ${mention.deterministic} resolved by the deterministic index, ${mention.openai} by the OpenAI step, ${mention.unresolved} unresolved (no matching node, or the model answered "none"), ${mention.generic} generic ("patients", "neurons"…) skipped, ${mention.not_in_graph ?? 0} gene symbols outside the slice. OpenAI picks outside the candidate list rejected: ${mention.openai_rejected_not_in_candidates}.`, '',
    '| Method | Mentions |', '|---|---|',
    ...Object.entries(rec.stats.methods).sort((x, y) => y[1] - x[1]).map(([k, v]) => `| ${k} | ${v} |`), '',
    ...((rec.duplicate_node_suspects ?? []).length ? [
      '**One entity, several nodes (for the curators).** These names are shared by two nodes of the same type in the curated graph, so claims about them cannot reconcile to one stable node. Merging or cross-linking them is a curation decision:', '',
      ...rec.duplicate_node_suspects.map((s) => `- "${esc(s.shared_name)}" (${s.type}): ${s.node_ids.map((i) => `\`${i}\``).join(', ')}`), '',
    ] : []),
    'Claims dropped by the mapping rules (endpoints resolved but not comparable):', '',
    ...Object.entries(claimStats.dropped).map(([k, v]) => `- ${k}: ${v}`), '',
    'Mapping rules (fixed, in `compare.mjs`): `causes` is lifted from a variant class to its gene; a gene or gene-level variant claim about an effect becomes `disease:<GENE> driven_by`; a variant-class effect is compared on `vg:… has_effect` and, as the curators do, also on the disease\'s `driven_by` edge; `has_phenotype` claims seen only in animal or cell models are not compared; "opposite effect class" means gain of function versus loss of function, haploinsufficiency, dominant-negative or destabilization of the same gene, and is flagged only where the graph lacks the claimed effect or the curators cite the same paper.', '');

  if (negativeNoEdge.length) {
    p('## Negative findings with no edge', '', 'Negated claims whose relation is not in the graph (nothing to contradict, kept for context):', '');
    for (const x of negativeNoEdge.slice(0, 15)) p(`- \`${x.edge_id}\` (PMID:${x.claim.pmid}): "${esc(x.claim.quote)}"`);
    p('');
  }

  p('## Usage consumed', '',
    '| Step | Requests OK | Failed | Input tokens | Output tokens (reasoning) | Summed request time |', '|---|---|---|---|---|---|',
    ...scripts.map((s) => {
      const okS = ok.filter((u) => u.script === s);
      return `| ${s} | ${okS.length} | ${failures.filter((u) => u.script === s).length} | ${sum(okS, 'input_tokens').toLocaleString('en-US')} | ${sum(okS, 'output_tokens').toLocaleString('en-US')} (${reasoning(okS).toLocaleString('en-US')}) | ${(ms(okS) / 60000).toFixed(1)} min |`;
    }),
    `| **total** | **${ok.length}** | **${failures.length}** | **${sum(ok, 'input_tokens').toLocaleString('en-US')}** | **${sum(ok, 'output_tokens').toLocaleString('en-US')}** | **${(ms(ok) / 60000).toFixed(1)} min** |`, '',
    `All requests used the ChatGPT-plan path (\`authMode: "chatgpt"\`); \`OPENAI_API_KEY\` was never used. Models seen: ${[...new Set(ok.map((u) => u.model))].map((m) => `\`${m}\``).join(', ')}. Structured mode: ${[...new Set(ok.map((u) => u.structured_mode))].join(', ')}. At most 2 requests were in flight.`,
    stops.length ? `**Stopped early:** ${stops.join('; ')}. Finished work is cached; rerun the same command to continue.` : 'No usage-limit or plan errors were hit.',
    failures.length ? `Failures: ${failures.map((f) => `${f.script} ${f.pmid}: ${f.error?.kind}`).join('; ')}.` : '', '');

  p('## How to re-run', '',
    '```bash',
    'node integrations/openai/cli.mjs status          # signed in, plan usage ENABLED',
    'node pipeline/openai/extract.mjs                 # biology abstracts (cached per PMID: reruns are free)',
    'node pipeline/openai/extract.mjs --set community --limit 50   # more community abstracts, priority order',
    'node pipeline/openai/reconcile.mjs               # deterministic index + one batched OpenAI call per abstract (cached)',
    'node pipeline/openai/compare.mjs                 # no calls: crosscheck.json, openai_extracted.json, this report',
    'python3 pipeline/build_graph.py                  # applies crosscheck.json and merges the fragment',
    '```', '',
    '`extract.mjs --verify-only` re-verifies every cached quote without calling the model. `reconcile.mjs --no-llm` runs the deterministic index only. Caches: `data/raw/openai/extractions/<PMID>.json` (model, generated_at, raw response, usage), `data/raw/openai/reconcile/<PMID>.json` (request payload, raw response, per-mention decisions). Every request is logged in `data/raw/openai/usage_log.jsonl`.', '');

  p('## Caveats', '',
    '- Only title + abstract were sent. Investigators are not extracted by the model (no author list is sent); researcher nodes come from PubMed author metadata in the community layer.',
    '- The model sees the abstract only; curators sometimes filed a PMID from a specific sentence with a narrower meaning. A disagreement is a prompt to look, not a verdict.',
    '- Candidate edges and synonyms are proposals: `status: "unverified"`, `attrs.needs_review: true`, confidence ≤ 0.5.',
    '- Run on a personal ChatGPT Plus plan (see risk 5 in `docs/openai-integration.md`): the batch was kept small and cached.', '');

  writeFileSync(REPORT, `${L.join('\n')}\n`);
}
