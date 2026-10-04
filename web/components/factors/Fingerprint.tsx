"use client";

// "Disease fingerprint": the seven factors for one disease, in a fixed order.
//  - AtlasFingerprint: the 45 in-depth diseases (graph + mechsim profile + per-gene data + direction layer).
//  - GlobalFingerprint: any disease in the global index (per-gene data + G2P/Reactome mechanism shard + HPO).
import { useDerived } from "@/lib/derived";
import { useDirection } from "@/lib/direction";
import { loadGeneFeatures, loadMechClass, sumTypes, typeSentence, type GeneFeature, type MechClass, type MechsimData } from "@/lib/factors";
import { GLOBAL_BASE, bucketOf, type GlobalRow, type NeighbourEntry } from "@/lib/global";
import type { GraphIndex } from "@/lib/graph";
import { diseaseContext, phenotypeIc } from "@/lib/insights";
import { useResource } from "@/lib/resource";
import type { AtlasNode } from "@/lib/types";
import { FingerprintTable, SpectrumMini, TypeSpectrumMini, topSpectrumWords, type FingerprintRow } from "./FactorBits";

const loaders = new Map<string, () => Promise<Record<string, GeneFeature>>>();
function geneLoader(joined: string) {
  let l = loaders.get(joined);
  if (!l) loaders.set(joined, (l = () => loadGeneFeatures(joined.split(",").filter(Boolean))));
  return l;
}
export function useGeneFeatures(genes: string[]): Record<string, GeneFeature> | null {
  const joined = genes.slice(0, 6).join(",");
  return useResource<Record<string, GeneFeature>>(joined ? `gf:${joined}` : null, geneLoader(joined))?.data ?? null;
}
export function useMechClass(): MechClass | null {
  return useResource<MechClass>("web:mechclass", loadMechClass)?.data ?? null;
}

const Chip = ({ children, href }: { children: React.ReactNode; href?: string }) =>
  href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className="mr-1.5 mb-1 inline-block rounded-full border border-line px-2 py-0.5 text-xs text-ink-2 hover:border-accent-500">
      {children}
    </a>
  ) : (
    <span className="mr-1.5 mb-1 inline-block rounded-full bg-subtle px-2 py-0.5 text-xs text-ink-2">{children}</span>
  );

const DIR_WORDS: Record<string, [string, string]> = {
  LoF: ["Loss of function (too little of the protein’s activity)", "the gene change leaves too little of the protein’s activity"],
  GoF: ["Gain of function (too much activity)", "the gene change makes the protein too active"],
  mixed: ["Both, depending on the variant (loss and gain of function)", "some changes lower the protein’s activity and others raise it"],
};
const CLASS_WORDS: Record<string, string> = {
  "mech:loss-of-function": "loss of function",
  "mech:haploinsufficiency": "haploinsufficiency (one working copy is not enough)",
  "mech:gain-of-function": "gain of function",
  "mech:dominant-negative": "dominant negative (the altered protein blocks the normal one)",
  "mech:lysosomal-enzyme-deficiency": "enzyme deficiency",
  "mech:protein-destabilization": "unstable protein",
};

function tissueBits(feats: GeneFeature[]) {
  const t: Record<string, number> = {};
  for (const f of feats) for (const [k, v] of Object.entries(f.tis ?? {})) t[k] = Math.max(t[k] ?? 0, v);
  const top = Object.entries(t).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k]) => k);
  const spec = feats.find((f) => f.hpa)?.hpa ?? null;
  return { top, spec };
}

function structureBits(feats: GeneFeature[], pfamNames?: MechsimData["pfam"]) {
  const pfam = [...new Set(feats.flatMap((f) => f.pfam ?? []))];
  const panther = [...new Set(feats.flatMap((f) => f.panther ?? []))];
  const uni = feats.find((f) => f.uni)?.uni ?? null;
  return { pfam: pfam.map((p) => ({ id: p, name: pfamNames?.[p]?.name ?? null, desc: pfamNames?.[p]?.description ?? null })), panther, uni };
}

function sumSpec(feats: GeneFeature[]) {
  const c: Record<string, number> = {};
  let n = 0;
  for (const f of feats) {
    n += f.n ?? 0;
    for (const [k, v] of Object.entries(f.c ?? {})) c[k] = (c[k] ?? 0) + v;
  }
  return n ? { c, n, t: sumTypes(feats) } : null;
}

function commonRows(genes: string[], feats: GeneFeature[], pfamNames?: MechsimData["pfam"]): FingerprintRow[] {
  const rows: FingerprintRow[] = [];
  const g0 = genes[0];
  if (genes.length)
    rows.push({
      key: "gene",
      value: (
        <>
          {genes.slice(0, 8).map((g) => (
            <Chip key={g} href={`https://www.genenames.org/tools/search/#!/?query=${encodeURIComponent(g)}`}>
              <span className="font-mono">{g}</span>
            </Chip>
          ))}
          {genes.length > 8 && <span className="text-xs text-ink-3">+{genes.length - 8} more</span>}
        </>
      ),
      plain: genes.length === 1 ? `Caused by changes in one gene, ${g0}.` : `Caused by changes in ${genes.length} genes, including ${genes.slice(0, 3).join(", ")}.`,
      source: g0 ? { label: "HGNC", url: `https://www.genenames.org/tools/search/#!/?query=${encodeURIComponent(g0)}` } : null,
    });
  const tb = tissueBits(feats);
  if (tb.top.length || tb.spec)
    rows.push({
      key: "tissue",
      value: (
        <>
          {tb.top.map((t) => (
            <Chip key={t}>{t}</Chip>
          ))}
          {tb.spec && <span className="text-xs text-ink-3">{tb.spec} (Human Protein Atlas)</span>}
        </>
      ),
      plain: tb.top.length ? `The gene is most active in the ${tb.top.slice(0, 2).join(" and ")}.` : `The gene is active in many tissues (${(tb.spec ?? "").toLowerCase()}).`,
      source: g0 ? { label: "Human Protein Atlas", url: `https://www.proteinatlas.org/search/${encodeURIComponent(g0)}` } : null,
    });
  const sb = structureBits(feats, pfamNames);
  if (sb.pfam.length || sb.panther.length || sb.uni)
    rows.push({
      key: "structure",
      value: (
        <>
          {sb.pfam.slice(0, 4).map((p) => (
            <Chip key={p.id} href={`https://www.ebi.ac.uk/interpro/entry/pfam/${p.id}/`}>
              {p.name ? `${p.name} (${p.id})` : p.id}
            </Chip>
          ))}
          {sb.panther.slice(0, 2).map((p) => (
            <Chip key={p} href={`https://www.pantherdb.org/panther/family.do?clsAccession=${p}`}>
              PANTHER {p}
            </Chip>
          ))}
          {sb.uni && (
            <a href={`https://alphafold.ebi.ac.uk/entry/${sb.uni}`} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-accent-700 hover:underline">
              AlphaFold structure available ↗
            </a>
          )}
        </>
      ),
      plain: `Protein family: ${sb.pfam[0]?.desc ?? sb.pfam[0]?.name ?? sb.panther[0] ?? "not recorded"}.${sb.uni ? " A 3D model of the protein (AlphaFold) exists." : ""}`,
      source: sb.uni ? { label: "UniProt", url: `https://www.uniprot.org/uniprotkb/${sb.uni}` } : null,
    });
  const sp = sumSpec(feats);
  if (sp)
    rows.push({
      key: "mutation",
      value: sp.t ? (
        <>
          <TypeSpectrumMini t={sp.t} n={sp.n} />
          {topSpectrumWords(sp.c) && <span className="mt-0.5 block text-xs text-ink-3">Effect on the protein: mostly {topSpectrumWords(sp.c)}.</span>}
        </>
      ) : (
        <SpectrumMini c={sp.c} n={sp.n} />
      ),
      plain: sp.t
        ? `The disease-causing DNA changes are mostly ${typeSentence(sp.t) ?? "of mixed kinds"}.`
        : `Most disease-causing changes are ${topSpectrumWords(sp.c) ?? "of mixed types"}.`,
      source: g0 ? { label: "ClinVar", url: `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(`${g0}[gene] AND (pathogenic[clinsig] OR likely_pathogenic[clinsig])`)}` } : null,
    });
  return rows;
}

/** Atlas disease (one of the 45 mapped in depth). */
export function AtlasFingerprint({ idx, node, plain = false, open = true }: { idx: GraphIndex; node: AtlasNode; plain?: boolean; open?: boolean }) {
  const rows = useAtlasRows(idx, node);
  return <FingerprintTable rows={rows} plain={plain} open={open} />;
}

/** The seven fingerprint rows of an atlas disease (also used side by side on /compare). */
export function useAtlasRows(idx: GraphIndex, node: AtlasNode): FingerprintRow[] {
  const ms = useDerived<MechsimData>("mechsim");
  const dir = useDirection();
  const ctx = diseaseContext(idx, node.id);
  const genes = (ctx?.genes ?? []).map((g) => g.label);
  const feats = useGeneFeatures(genes);
  const data = ms.status === "ready" ? ms.data : null;
  const prof = data?.profiles.find((p) => p.id === node.id) ?? null;
  const fl = genes.map((g) => feats?.[g]).filter((f): f is GeneFeature => !!f);
  const rows = commonRows(genes, fl, data?.pfam);

  // pathway: the most specific (smallest) Reactome sets first
  if (prof && data) {
    const sets = prof.pathways
      .map((id) => ({ id, ...data.pathway_sets[id] }))
      .filter((s) => s.name)
      .sort((a, b) => Number(/reactome/i.test(b.origin)) - Number(/reactome/i.test(a.origin)) || a.size - b.size)
      .filter((x, i, all) => all.findIndex((y) => y.name.toLowerCase() === x.name.toLowerCase()) === i);
    if (sets.length)
      rows.push({
        key: "pathway",
        value: (
          <>
            {sets.slice(0, 4).map((s) => (
              <Chip key={s.id} href={s.url}>
                {s.name}
              </Chip>
            ))}
            {sets.length > 4 && <span className="text-xs text-ink-3">+{sets.length - 4} more</span>}
          </>
        ),
        plain: `It works in ${sets.slice(0, 2).map((s) => s.name.toLowerCase()).join(" and ")}.`,
        source: { label: "MSigDB / Reactome", url: sets[0].url },
      });
    const anchors = (prof.tissue?.symptoms ?? []).slice(0, 2).map(([t]) => t);
    const tissueRow = rows.find((r) => r.key === "tissue");
    if (anchors.length) {
      const extra = <span className="mt-0.5 block text-xs text-ink-3">Symptoms point to: {anchors.join(", ")}</span>;
      if (tissueRow) tissueRow.value = <>{tissueRow.value}{extra}</>;
      else rows.push({ key: "tissue", value: extra, plain: `The symptoms point to the ${anchors[0]}.`, source: null });
    }
  }

  // symptoms: the most distinctive HPO terms (information content)
  const ph = [...(ctx?.phenotypes.keys() ?? [])]
    .map((pid) => idx.nodeById.get(pid))
    .filter((n): n is AtlasNode => !!n)
    .sort((a, b) => phenotypeIc(idx, b) - phenotypeIc(idx, a));
  if (ph.length)
    rows.push({
      key: "symptoms",
      value: (
        <>
          {ph.slice(0, 6).map((p) => (
            <Chip key={p.id}>{p.label}</Chip>
          ))}
          <span className="text-xs text-ink-3">{ph.length} recorded, most distinctive first</span>
        </>
      ),
      plain: `Its most telling signs include ${ph.slice(0, 3).map((p) => p.label.toLowerCase()).join(", ")}.`,
      source: { label: "HPO", url: "https://hpo.jax.org/" },
    });

  // molecular consequence: direction layer + mechsim protein fate
  const d = dir?.diseases[node.id]?.d ?? null;
  const fateTop = prof?.fate
    ? prof.fate.vector
        .map((v, i) => ({ v, label: data?.meta.fate_labels[prof.fate!.labels[i]] ?? prof.fate!.labels[i] }))
        .filter((x) => x.v >= 0.1)
        .sort((a, b) => b.v - a.v)
        .slice(0, 3)
    : [];
  if (d || fateTop.length)
    rows.push({
      key: "fate",
      value: (
        <>
          {d && <span className="font-medium text-ink">{DIR_WORDS[d]?.[0] ?? d}</span>}
          {fateTop.length > 0 && (
            <span className="mt-0.5 block text-xs text-ink-3">
              Predicted protein fate: {fateTop.map((x) => `${x.label} ${Math.round(x.v * 100)}%`).join(" · ")}
            </span>
          )}
        </>
      ),
      plain: d ? `In plain words: ${DIR_WORDS[d]?.[1] ?? d}.` : "What the change does to the protein is still being worked out.",
      source: genes[0] ? { label: "G2P / atlas evidence", url: `https://www.ebi.ac.uk/gene2phenotype/search?query=${encodeURIComponent(genes[0])}` } : null,
    });
  return rows;
}

interface MechShard {
  p: Record<string, string>;
  d: Record<string, { mechanisms?: { class: string | null; source: string; url: string }[]; pathways?: string[] }>;
}
const mechLoaders = new Map<number, () => Promise<MechShard>>();
function mechLoader(b: number) {
  let l = mechLoaders.get(b);
  if (!l) mechLoaders.set(b, (l = () => fetch(`${GLOBAL_BASE}/mechanism/${b}.json`).then((r) => r.json() as Promise<MechShard>)));
  return l;
}

/** Any disease in the global index. */
export function GlobalFingerprint({ row, entry, terms, plain = false, open = true }: { row: GlobalRow; entry?: NeighbourEntry | null; terms: Record<string, [string, number]>; plain?: boolean; open?: boolean }) {
  const feats = useGeneFeatures(row.genes);
  const mc = useMechClass();
  const b = bucketOf(row.id);
  const shard = useResource<MechShard>(`global:mechanism:${b}`, mechLoader(b))?.data ?? null;
  const fl = row.genes.map((g) => feats?.[g]).filter((f): f is GeneFeature => !!f);
  const rows = commonRows(row.genes, fl);
  const me = shard?.d[row.id];
  if (me?.pathways?.length)
    rows.push({
      key: "pathway",
      value: (
        <>
          {me.pathways.slice(0, 4).map((p) => (
            <Chip key={p} href={`https://reactome.org/content/detail/${p}`}>
              {shard?.p[p] ?? p}
            </Chip>
          ))}
          {me.pathways.length > 4 && <span className="text-xs text-ink-3">+{me.pathways.length - 4} more</span>}
        </>
      ),
      plain: `It works in ${me.pathways.slice(0, 2).map((p) => (shard?.p[p] ?? p).toLowerCase()).join(" and ")}.`,
      source: { label: "Reactome", url: `https://reactome.org/content/detail/${me.pathways[0]}` },
    });
  const own = entry?.own ?? [];
  if (own.length)
    rows.push({
      key: "symptoms",
      value: (
        <>
          {own.slice(0, 6).map((h) => (
            <Chip key={h} href={`https://hpo.jax.org/browse/term/${h}`}>
              {terms[h]?.[0] ?? h}
            </Chip>
          ))}
          <span className="text-xs text-ink-3">most distinctive first</span>
        </>
      ),
      plain: `Its most telling signs include ${own.slice(0, 3).map((h) => (terms[h]?.[0] ?? h).toLowerCase()).join(", ")}.`,
      source: { label: "HPO", url: `https://hpo.jax.org/browse/term/${own[0]}` },
    });
  const classes = [...new Set((me?.mechanisms ?? []).map((m) => m.class).filter((c): c is string => !!c))];
  const d = mc?.[row.id]?.d ?? null;
  if (classes.length || d)
    rows.push({
      key: "fate",
      value: (
        <>
          {d && <span className="font-medium text-ink">{DIR_WORDS[d]?.[0] ?? d}</span>}
          {classes.length > 0 && (
            <span className="mt-0.5 block text-xs text-ink-3">
              Mechanism class: {classes.map((c) => CLASS_WORDS[c] ?? c.replace(/^mech:/, "").replace(/-/g, " ")).join(", ")} ({[...new Set((me?.mechanisms ?? []).map((m) => m.source))].join(", ")})
            </span>
          )}
        </>
      ),
      plain: d ? `In plain words: ${DIR_WORDS[d]?.[1] ?? d}.` : `Recorded mechanism: ${classes.map((c) => CLASS_WORDS[c] ?? c.replace(/^mech:/, "")).join(", ")}.`,
      source: me?.mechanisms?.[0]?.url ? { label: me.mechanisms[0].source, url: me.mechanisms[0].url } : null,
    });
  return <FingerprintTable rows={rows} plain={plain} open={open} />;
}
