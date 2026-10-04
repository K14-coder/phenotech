"use client";

// /d/<id>: a page for any rare disease outside the families the atlas maps in depth. Basic data only
// (lib/global.ts): the disease's own most distinctive symptoms, the diseases with the most similar
// symptom patterns, how close it sits to the mapped families, and links out. Lookups, not evidence:
// no confidence scores, no graph edges.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import { WithGraph } from "../GraphProvider";
import { SearchBox } from "../search/SearchBox";
import { familyName } from "@/lib/bridges";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import type { AtlasNode, Cluster } from "@/lib/types";
import {
  GLOBAL_INDEX_KEY,
  GLOBAL_META_KEY,
  fillTemplate,
  globalIdFromParam,
  isGlobalId,
  loadGlobalIndex,
  mappedAtlasId,
  normalizeTerm,
  loadGlobalMeta,
  loadShard,
  rowHref,
  shardKey,
  type GlobalIndex,
  type GlobalMeta,
  type GlobalRow,
  type NeighbourEntry,
  type NeighbourShard,
} from "@/lib/global";
import { retry, useResource } from "@/lib/resource";
import { usePersona } from "@/lib/persona";
import { loadScale, type ScaleEntry } from "@/lib/population";
import { DevonPage } from "../devon/DevonPage";
import { JoinBox } from "../community/JoinBox";
import { buildGlobalDevonModel } from "../devon/devonGlobal";
import { DisMechIfAny, MechanismLayer } from "./MechanismBits";
import { CommunityResearch } from "../queue/CommunityResearch";
import { capFirst, joinList, plural } from "@/lib/text";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";
/** IC at or above this is "distinctive" (meta.method.distinctive_ic; the atlas uses the same cut-off) */
const DEFAULT_DISTINCTIVE_IC = 4;

type Terms = NeighbourShard["t"];

export function GlobalDiseaseView({ param }: { param: string }) {
  const id = globalIdFromParam(param);
  return <WithGraph>{(idx) => <GlobalDisease idx={idx} id={id} />}</WithGraph>;
}

function GlobalDisease({ idx, id }: { idx: GraphIndex; id: string }) {
  const router = useRouter();
  const indexRes = useResource<GlobalIndex>(GLOBAL_INDEX_KEY, loadGlobalIndex);
  const metaRes = useResource<GlobalMeta>(GLOBAL_META_KEY, loadGlobalMeta);
  const loadNeighbours = useCallback(() => loadShard<NeighbourShard>("neighbours", id), [id]);
  const shardRes = useResource<NeighbourShard>(isGlobalId(id) ? shardKey("neighbours", id) : null, loadNeighbours);
  const persona = usePersona();
  const loadScaleEntry = useCallback(() => loadScale(id), [id]);
  const scaleRes = useResource<ScaleEntry | null>(isGlobalId(id) ? `web:scale:${id}` : null, loadScaleEntry);
  const gi = indexRes?.data;
  const row = gi?.byId.get(id);
  const mapped = row ? mappedAtlasId(row, idx) : null;

  // a disease the atlas maps in depth has its full action page
  useEffect(() => {
    if (mapped) router.replace(diseaseHref(mapped));
  }, [mapped, router]);
  // the route's static metadata title is generic; name the tab after the disease (again after Next
  // re-applies the static title on client navigation between /d/ pages)
  useEffect(() => {
    if (!row) return;
    const title = `${capFirst(row.name)} · Rare Disease Atlas`;
    document.title = title;
    const t = setTimeout(() => {
      document.title = title;
    }, 80);
    return () => clearTimeout(t);
  }, [row]);

  if (indexRes?.status === "error")
    return (
      <Centered>
        <p className="text-sm font-medium text-ink">The rare-disease index could not be loaded.</p>
        <p className="mt-2 text-sm text-ink-3">{indexRes.error}</p>
        <button
          type="button"
          onClick={() => retry(GLOBAL_INDEX_KEY, loadGlobalIndex)}
          className="mt-4 rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
        >
          Try again
        </button>
      </Centered>
    );
  if (!gi)
    return (
      <Centered>
        <p className="text-sm text-ink-3" role="status" aria-live="polite">
          Loading the rare-disease index…
        </p>
      </Centered>
    );
  if (!row) return <NotFound id={id} />;
  if (mapped)
    return (
      <Centered>
        <p className="text-sm text-ink-3" role="status">
          This disease is mapped in depth. Opening its atlas page…
        </p>
      </Centered>
    );

  const meta = metaRes?.data;
  const entry = shardRes?.data?.d[id] ?? null;
  const terms: Terms = shardRes?.data?.t ?? {};
  const shardState: "loading" | "ready" | "error" = shardRes?.status ?? "loading";
  const icCut = meta?.method?.distinctive_ic ?? DEFAULT_DISTINCTIVE_IC;
  const families = idx.graph.clusters.filter((c) => c.basis === "pathway");
  const mappedDiseases = idx.graph.nodes.filter((n) => n.type === "disease").length;
  const scope = families.length
    ? `${plural(families.length, "disease family", "disease families")} in depth today (${families.map(familyName).join("; ")})`
    : `${plural(mappedDiseases, "disease")} in depth today`;
  const related = relatedAtlasDiseases(idx, row);
  const inheritance = entry?.inh.map((h) => terms[h]?.[0] ?? h) ?? [];

  const detail = (
    <div className={persona === "family" ? "" : "pb-24"}>
      <header className="border-b border-line">
        <div className="mx-auto max-w-[1120px] px-8 pb-8 pt-7">
          <nav aria-label="Breadcrumb" className="text-xs text-ink-3">
            <Link href="/" className="hover:text-ink">
              Search
            </Link>
            <span className="mx-1.5">/</span>
            <span>Rare diseases (basic data)</span>
          </nav>
          <div className="mt-4 flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-[700px]">
              <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-ink">{capFirst(row.name)}</h1>
              {row.syn.length > 0 && <p className="mt-1.5 text-sm text-ink-3">Also called {row.syn.join(", ")}</p>}
              <div className="mt-5 rounded-lg bg-subtle px-4 py-3.5">
                {related.length ? (
                  <p className="text-[15px] leading-relaxed text-ink">
                    <span className="font-semibold">Mapped in basic form here.</span> The atlas maps {scope}. One of its in-depth diseases lists “
                    {row.name}” among its names:{" "}
                    {related.map((n, i) => (
                      <span key={n.id}>
                        {i > 0 && ", "}
                        <Link href={diseaseHref(n.id)} className="font-medium text-accent-700 hover:underline">
                          {n.label} →
                        </Link>
                      </span>
                    ))}
                  </p>
                ) : (
                  <p className="text-[15px] leading-relaxed text-ink">
                    <span className="font-semibold">Mapped in basic form.</span> The atlas maps {scope}; this disease isn’t one of them yet.
                  </p>
                )}
                <p className="mt-1.5 text-sm leading-relaxed text-ink-3">
                  What you see here: {meta?.caveat ?? "phenotype similarity only; no evidence curation; mechanism not assessed"}.
                </p>
              </div>
              <ExternalLinks row={row} meta={meta} />
            </div>
            <dl className="w-full shrink-0 divide-y divide-line-2 rounded-lg border border-line px-4 lg:w-[300px]">
              <FactRow k={row.genes.length === 1 ? "Gene" : "Genes"}>
                {row.genes.length ? joinList(row.genes, 6) : "None recorded"}
                {row.gsrc === 2 && <span className="mt-0.5 block text-xs text-ink-3">From Orphanet only; may include modifier genes</span>}
              </FactRow>
              <FactRow k="Inheritance">
                {shardState === "loading" ? <span className="text-ink-3">Loading…</span> : inheritance.length ? inheritance.join("; ") : "Not annotated"}
              </FactRow>
              <FactRow k="Annotated symptoms">{row.n}</FactRow>
              <FactRow k="Identifiers">
                <span className="break-words">{[row.id, ...row.omim.map((o) => `OMIM:${o}`), ...row.orpha.map((o) => `ORPHA:${o}`)].join(" · ")}</span>
              </FactRow>
            </dl>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1120px] space-y-14 px-8 pt-12">
        {/* curated mechanism records (same djb2 bucketing) and DisMech's independent chain */}
        <MechanismLayer id={row.id} gi={gi} />
        <DisMechIfAny mondo={row.id} />
        <CommunityResearch id={row.id} />

        {shardState === "error" ? (
          <p className="max-w-[760px] rounded-lg border border-dashed border-ink-4 px-5 py-4 text-sm text-ink-2">
            The symptom comparison for this disease could not be loaded. {shardRes?.error}
          </p>
        ) : shardState === "loading" ? (
          <p className="text-sm text-ink-3" role="status" aria-live="polite">
            Loading the symptom comparison…
          </p>
        ) : !entry ? (
          <p className="max-w-[760px] rounded-lg border border-dashed border-ink-4 px-5 py-4 text-sm leading-relaxed text-ink-2">
            {row.n} annotated {row.n === 1 ? "symptom" : "symptoms"}: too few to compare with other diseases. The links above lead to what
            is known.
          </p>
        ) : (
          <>
            <Distinctive entry={entry} terms={terms} icCut={icCut} meta={meta} />
            <Similar entry={entry} terms={terms} icCut={icCut} gi={gi} idx={idx} />
            <Closest idx={idx} entry={entry} terms={terms} meta={meta} families={families} compared={comparedFamilies(families, shardRes?.data)} />
          </>
        )}

        <section aria-labelledby="map-h" className="max-w-[760px]">
          <p className={EYEBROW}>Next</p>
          <h2 id="map-h" className={`mt-1 ${H2}`}>
            How the atlas would map it in depth
          </h2>
          <ol className="mt-4 list-decimal space-y-2 pl-5 text-[15px] leading-relaxed text-ink-2">
            <li>Collect the evidence: whether the gene really causes the disease, how its variants act, and the papers behind each claim.</li>
            <li>Check every link against its source, quote by quote, and grade how strong it is.</li>
            <li>Group it with diseases that share the mechanism, then add the patient groups, registries and trials that serve it.</li>
          </ol>
          <p className="mt-4 text-sm text-ink-2">
            Know a patient group, registry or study for this disease?{" "}
            <Link href="/contribute" className="font-medium text-accent-700 hover:underline">
              Contribute what you know →
            </Link>
          </p>
        </section>
      </div>
    </div>
  );

  const join = <JoinBox diseaseId={row.id} diseaseName={capFirst(row.name)} />;
  if (persona === "family")
    return (
      <>
        <DevonPage
          m={buildGlobalDevonModel(row, entry, terms, scaleRes?.data ?? null, shardState === "loading" || scaleRes?.status === "loading")}
          learnMore={detail}
        />
        {join}
      </>
    );
  return (
    <>
      {detail}
      {join}
    </>
  );
}

function Distinctive({ entry, terms, icCut, meta }: { entry: NeighbourEntry; terms: Terms; icCut: number; meta?: GlobalMeta }) {
  const hpoUrl = meta?.url_templates?.HPO_term;
  return (
    <section aria-labelledby="own-h" className="max-w-[760px]">
      <p className={EYEBROW}>Symptoms</p>
      <h2 id="own-h" className={`mt-1 ${H2}`}>
        Most distinctive symptoms
      </h2>
      <p className="mt-1.5 text-sm text-ink-3">
        The most specific annotated symptoms (HPO). <span className="text-ink-2">Distinctive</span> ones are rare across all diseases;
        broad ones are common.
      </p>
      <ul className="mt-4 divide-y divide-line-2 border-y border-line-2">
        {entry.own.slice(0, 8).map((h) => {
          const [label, ic] = terms[h] ?? [h, 0];
          const distinctive = ic >= icCut;
          return (
            <li key={h} className="flex items-baseline justify-between gap-4 py-2 text-[15px]">
              {hpoUrl ? (
                <a href={fillTemplate(hpoUrl, { hpo: h })} target="_blank" rel="noopener noreferrer" className="text-ink hover:text-accent-700 hover:underline">
                  {label}
                </a>
              ) : (
                <span className="text-ink">{label}</span>
              )}
              <span className="shrink-0 text-xs text-ink-3" title={`Information content ${ic.toFixed(1)} (${h})`}>
                <span className={distinctive ? "text-ink-2" : ""}>{distinctive ? "distinctive" : "broad"}</span> · IC {ic.toFixed(1)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Atlas diseases that list this disease's name (or a synonym) among their own names, e.g. Dravet syndrome -> SCN1A. */
function relatedAtlasDiseases(idx: GraphIndex, row: GlobalRow): AtlasNode[] {
  const names = new Set([row.name, ...row.syn].map(normalizeTerm).filter((t) => t.length > 3));
  return idx.graph.nodes.filter((n) => n.type === "disease" && [n.label, ...(n.synonyms ?? [])].some((s) => names.has(normalizeTerm(s))));
}

/**
 * Which mapped families the symptom comparison covers: the families of every atlas disease that
 * appears in this shard's comparisons. A family added after the comparison was computed is not
 * covered until the global index is rebuilt, and the page says so.
 */
function comparedFamilies(families: Cluster[], shard?: NeighbourShard): Cluster[] {
  if (!shard) return families;
  const ids = new Set(Object.values(shard.d).flatMap((e) => e.atlas.map((a) => a[0])));
  return families.filter((c) => c.members.some((m) => ids.has(m)));
}

function Similar({ entry, terms, icCut, gi, idx }: { entry: NeighbourEntry; terms: Terms; icCut: number; gi: GlobalIndex; idx: GraphIndex }) {
  if (!entry.nb.length) return null;
  return (
    <section aria-labelledby="nb-h" className="max-w-[760px]">
      <p className={EYEBROW}>Look-alikes</p>
      <h2 id="nb-h" className={`mt-1 ${H2}`}>
        Diseases with the most similar symptom patterns
      </h2>
      <p className="mt-1.5 text-sm text-ink-3">Ranked by how much of the symptom pattern they share, weighted towards the specific symptoms.</p>
      <ol className="mt-4 space-y-3">
        {entry.nb.slice(0, 10).map(([nid, score, , shared], i) => {
          const r = gi.byId.get(nid);
          const name = r ? capFirst(r.name) : nid;
          return (
            <li key={nid} className="flex gap-3">
              <span className="w-5 shrink-0 pt-0.5 text-right text-sm tabular-nums text-ink-3">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  {r ? (
                    <Link href={rowHref(r, idx)} className="text-[15px] font-medium text-ink hover:text-accent-700 hover:underline">
                      {name}
                    </Link>
                  ) : (
                    <span className="text-[15px] font-medium text-ink">{name}</span>
                  )}
                  {r && mappedAtlasId(r, idx) && (
                    <span className="rounded-full border border-accent-200 px-2 py-0.5 text-[11px] text-accent-700">mapped in depth</span>
                  )}
                  <span className="text-xs tabular-nums text-ink-3">similarity {score.toFixed(2)}</span>
                </div>
                {shared.length > 0 && <SharedTerms ids={shared} terms={terms} icCut={icCut} />}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Closest({
  idx,
  entry,
  terms,
  meta,
  families,
  compared,
}: {
  idx: GraphIndex;
  entry: NeighbourEntry;
  terms: Terms;
  meta?: GlobalMeta;
  families: Cluster[];
  compared: Cluster[];
}) {
  const near = entry.atlas.filter((a) => a[3]);
  const top = entry.atlas[0];
  const label = (aid: string) => idx.nodeById.get(aid)?.label ?? aid.replace(/^disease:/, "");
  const notCompared = families.filter((c) => !compared.includes(c));
  const comparedNames = compared.map(familyName).join("; ");
  const coverage =
    notCompared.length > 0 ? (
      <p className="text-sm leading-relaxed text-ink-3">
        The symptom comparison doesn’t cover the newer mapped {notCompared.length === 1 ? "family" : "families"} yet (
        {notCompared.map(familyName).join("; ")}).
      </p>
    ) : null;
  return (
    <section aria-labelledby="closest-h" className="max-w-[760px]">
      <p className={EYEBROW}>The mapped families</p>
      <h2 id="closest-h" className={`mt-1 ${H2}`}>
        Closest disease in our mapped families
      </h2>
      {!entry.far && near.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {near.map(([aid, cos, , , shared]) => (
            <li key={aid} className="rounded-lg border border-line px-4 py-3">
              <p className="text-[15px] text-ink">
                Close to{" "}
                <Link href={diseaseHref(aid)} className="font-medium text-accent-700 hover:underline">
                  {label(aid)}
                </Link>{" "}
                <span className="text-xs tabular-nums text-ink-3">similarity {cos.toFixed(2)}</span>
              </p>
              {shared.length > 0 && <SharedTerms ids={shared} terms={terms} icCut={meta?.method?.distinctive_ic ?? DEFAULT_DISTINCTIVE_IC} />}
            </li>
          ))}
          <li className="text-sm leading-relaxed text-ink-3">
            “Close” means at least as similar as the least similar pair of diseases the atlas itself links. The mapped disease’s page shows the
            sourced evidence for its family.
          </li>
          {coverage && <li>{coverage}</li>}
        </ul>
      ) : (
        <div className="mt-4 space-y-2">
          <p className="text-[15px] leading-relaxed text-ink-2">
            {notCompared.length && compared.length
              ? `Its symptom pattern is far from the ${comparedNames}, so it most likely belongs to a different mechanism family.`
              : "Its symptom pattern is far from the families mapped in depth, so it most likely belongs to a different mechanism family."}
          </p>
          {coverage}
          {top && (
            <p className="text-sm text-ink-3">
              Nearest mapped disease:{" "}
              <Link href={diseaseHref(top[0])} className="text-accent-700 hover:underline">
                {label(top[0])}
              </Link>{" "}
              (similarity {top[1].toFixed(2)}, below the calibrated threshold).
            </p>
          )}
          {meta?.far_text && <p className="text-xs leading-relaxed text-ink-3">{meta.far_text}</p>}
        </div>
      )}
    </section>
  );
}

function SharedTerms({ ids, terms, icCut }: { ids: string[]; terms: Terms; icCut: number }) {
  return (
    <p className="mt-0.5 text-sm text-ink-3">
      Shares:{" "}
      {ids.map((h, i) => {
        const [label, ic] = terms[h] ?? [h, 0];
        return (
          <span key={h}>
            {i > 0 && " · "}
            <span className={ic >= icCut ? "text-ink-2" : ""} title={ic >= icCut ? "Distinctive" : "Broad"}>
              {label}
            </span>
          </span>
        );
      })}
    </p>
  );
}

function ExternalLinks({ row, meta }: { row: GlobalRow; meta?: GlobalMeta }) {
  const T = meta?.url_templates;
  if (!T) return null;
  const name = encodeURIComponent(row.name);
  const links: { label: string; href: string }[] = [
    ...row.omim.slice(0, 3).flatMap((o) => (T.OMIM ? [{ label: `OMIM ${o}`, href: fillTemplate(T.OMIM, { omim: o }) }] : [])),
    ...row.orpha.slice(0, 3).flatMap((o) => (T.Orphanet ? [{ label: `Orphanet ${o}`, href: fillTemplate(T.Orphanet, { orpha: o }) }] : [])),
    ...(row.id.startsWith("MONDO:") && T.MONDO_Monarch ? [{ label: "Monarch", href: fillTemplate(T.MONDO_Monarch, { mondo: row.id }) }] : []),
    ...(T.ClinicalTrials_condition_search ? [{ label: "ClinicalTrials.gov", href: fillTemplate(T.ClinicalTrials_condition_search, { name_urlencoded: name }) }] : []),
    ...(T.NORD_site_search ? [{ label: "NORD", href: fillTemplate(T.NORD_site_search, { name_urlencoded: name }) }] : []),
    ...(T.GeneReviews_search ? [{ label: "GeneReviews", href: fillTemplate(T.GeneReviews_search, { name_urlencoded: name }) }] : []),
  ];
  return (
    <ul className="mt-5 flex flex-wrap gap-2" aria-label="External resources">
      {links.map((l) => (
        <li key={l.label}>
          <a
            href={l.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex rounded-md border border-line px-2.5 py-1 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
          >
            {l.label} ↗
          </a>
        </li>
      ))}
    </ul>
  );
}

function FactRow({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-2.5 text-sm">
      <dt className="w-32 shrink-0 text-ink-3">{k}</dt>
      <dd className="min-w-0 flex-1 text-ink">{children}</dd>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-xl px-6 py-24 text-center">{children}</div>;
}

function NotFound({ id }: { id: string }) {
  return (
    <div className="mx-auto w-full max-w-xl px-6 py-24">
      <h1 className="text-xl font-semibold text-ink">We couldn’t find that disease</h1>
      <p className="mt-2 text-sm text-ink-3">“{id}” is not in the rare-disease index. Search by name, gene, or OMIM or Orphanet number.</p>
      <div className="mt-6">
        <SearchBox variant="field" autoFocus />
      </div>
    </div>
  );
}
