"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { WithGraph, useGraphReload } from "../GraphProvider";
import { useAi } from "../ai/AiProvider";
import { ContinueWithChatGPT } from "../ai/AiConnect";
import { atlasHref, diseaseHref, diseaseIdFromParam, type GraphIndex } from "@/lib/graph";
import { MANAGE_USAGE_URL } from "@/lib/ai-shared";
import { ASSET_KIND_LABEL } from "@/lib/text";

// ---------- response shapes (only what the UI reads; see docs/agent-reports/contribute.md) ----------

interface PreviewItem {
  index: number;
  status: "new" | "duplicate" | "rejected" | "unlinked" | "excluded";
  reason: string | null;
  reason_text: string | null;
  kind: string;
  name: string;
  asset_kind?: string | null;
  quote?: string | null;
  node_id?: string | null;
  verification?: { ok: boolean; verbatim?: boolean; reason?: string | null };
  mentions?: { mention: string; status: string }[];
  diseases?: { id: string; label: string; basis: string }[];
  duplicate_of?: { id: string; label: string; match: string; already_cites_url?: boolean; already_cited?: boolean } | null;
  edges?: { id: string; type: string; confidence: number; basis: string; status: string }[];
  warnings?: string[];
}

interface Preview {
  ok: true;
  url: string;
  requested_url: string;
  disease_id: string | null;
  contributor: string;
  page: { title?: string; via?: string; retrieved?: string; from_cache?: boolean; direct_problem?: string };
  extraction: { id: string; source: string; extracted_by?: string; model?: string; from_cache?: boolean; item_count?: number };
  items: PreviewItem[];
  summary: Record<string, number>;
  previous_contribution: { nodes: string[]; edges: string[] } | null;
  can_commit: boolean;
  [k: string]: unknown;
}

interface CommitResult {
  ok: true;
  changed: boolean;
  written: { nodes: string[]; edges: string[] };
  rebuild: { ran: boolean; ok?: boolean; reason?: string };
}

interface ApiError {
  code: string;
  message: string;
  llm?: { action?: string; manage_usage_url?: string };
  known_diseases?: string[];
}

interface ManualItem {
  kind: "asset" | "patient_org" | "study";
  name: string;
  asset_kind: string;
  quote: string;
  mentioned: string;
  what_it_offers: string;
  nct_id: string;
}

const EMPTY_ITEM: ManualItem = { kind: "asset", name: "", asset_kind: "registry", quote: "", mentioned: "", what_it_offers: "", nct_id: "" };

const STATUS_META: Record<PreviewItem["status"], { label: string; cls: string }> = {
  new: { label: "New", cls: "border-[#bcd9c6] bg-[#edf6f0] text-ok" },
  duplicate: { label: "Already in the atlas", cls: "border-accent-200 bg-accent-50 text-accent-900" },
  rejected: { label: "Rejected", cls: "border-warn-line bg-warn-bg text-warn-ink" },
  unlinked: { label: "Needs a disease", cls: "border-line bg-subtle text-ink-2" },
  excluded: { label: "Excluded", cls: "border-line bg-subtle text-ink-3" },
};

export function ContributeView() {
  return <WithGraph>{(idx) => <Contribute idx={idx} />}</WithGraph>;
}

function Contribute({ idx }: { idx: GraphIndex }) {
  const ai = useAi();
  const params = useSearchParams();
  const diseaseParam = params.get("disease");
  const gapId = params.get("gap");
  const gap = gapId ? idx.graph.gaps.find((g) => g.id === gapId) : undefined;
  const initialDisease = diseaseParam ? diseaseIdFromParam(diseaseParam) : "";
  const diseases = useMemo(() => idx.graph.nodes.filter((n) => n.type === "disease").sort((a, b) => a.label.localeCompare(b.label)), [idx]);

  if (!ai.loaded) return <p className="mx-auto max-w-[920px] px-8 py-16 text-sm text-ink-3">Loading…</p>;
  if (ai.status.mode !== "live") return <DeployedExplainer />;
  return <ContributeForm idx={idx} diseases={diseases} initialDisease={idx.nodeById.has(initialDisease) ? initialDisease : ""} gapQuestion={gap?.question} />;
}

function Header() {
  return (
    <>
      <p className="text-sm text-ink-3">Help the atlas grow</p>
      <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.02em] text-ink">Contribute what you know</h1>
    </>
  );
}

const HOW_IT_WORKS = [
  "Paste the web address of a page about something that already exists: a registry, a natural history study, a biobank, a model, a patient group.",
  "The atlas reads the page and proposes items. Each one must quote a sentence that is really on the page, word for word.",
  "It links each item to the diseases the page names, and spots entries the atlas already has (those just gain a new source).",
  "You review every item, untick anything wrong, and press “Add to the atlas”. Nothing is added before that.",
  "Additions are marked “Community-contributed · not yet reviewed” and drawn lighter on the map until an expert reviews them.",
];

function DeployedExplainer() {
  return (
    <div className="mx-auto w-full max-w-[860px] px-8 pb-24 pt-10">
      <Header />
      <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
        Contributions run on your own computer, because they read web pages, may use your ChatGPT plan and write to the atlas’s data files.
        Clone the repository, run <code className="rounded bg-subtle px-1.5 py-0.5 text-[13px]">npm install && npm run dev</code> in{" "}
        <code className="rounded bg-subtle px-1.5 py-0.5 text-[13px]">web/</code> (and optionally{" "}
        <code className="rounded bg-subtle px-1.5 py-0.5 text-[13px]">node integrations/openai/cli.mjs login</code>), then open{" "}
        <code className="rounded bg-subtle px-1.5 py-0.5 text-[13px]">http://127.0.0.1:3000/contribute</code>.
      </p>
      <h2 className="mt-10 text-[17px] font-semibold text-ink">How it works</h2>
      <ol className="mt-3 space-y-2.5">
        {HOW_IT_WORKS.map((s, i) => (
          <li key={s} className="grid grid-cols-[24px_minmax(0,1fr)] gap-2 text-[15px] leading-relaxed text-ink-2">
            <span className="tabular-nums text-ink-3">{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <p className="mt-6 text-sm text-ink-3">
        Without AI, the same flow accepts items typed by hand; they are verified against the page in exactly the same way.{" "}
        <Link href="/method" className="text-accent-700 hover:underline">
          How the atlas keeps evidence honest →
        </Link>
      </p>
    </div>
  );
}

function ContributeForm({
  idx,
  diseases,
  initialDisease,
  gapQuestion,
}: {
  idx: GraphIndex;
  diseases: { id: string; label: string }[];
  initialDisease: string;
  gapQuestion?: string;
}) {
  const ai = useAi();
  const reloadGraph = useGraphReload();
  const [url, setUrl] = useState("");
  const [disease, setDisease] = useState(initialDisease);
  const [contributor, setContributor] = useState("");
  const [manual, setManual] = useState(false);
  const [items, setItems] = useState<ManualItem[]>([{ ...EMPTY_ITEM }]);
  const [busy, setBusy] = useState<null | "preview" | "commit">(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [include, setInclude] = useState<Set<number>>(new Set());
  const [done, setDone] = useState<CommitResult | null>(null);
  const [reloaded, setReloaded] = useState(false);

  const post = async <T,>(path: string, body: unknown): Promise<{ ok: true; data: T } | { ok: false; error: ApiError }> => {
    try {
      const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
      const data = await r.json().catch(() => null);
      if (r.ok && data) return { ok: true, data: data as T };
      return { ok: false, error: (data?.error as ApiError) ?? { code: `http_${r.status}`, message: `The request failed (HTTP ${r.status}).` } };
    } catch (e) {
      return { ok: false, error: { code: "network", message: e instanceof Error ? e.message : String(e) } };
    }
  };

  const runPreview = async () => {
    setBusy("preview");
    setError(null);
    setDone(null);
    setPreview(null);
    const manualItems = manual
      ? items
          .filter((it) => it.name.trim() && it.quote.trim())
          .map((it) => ({
            kind: it.kind,
            name: it.name.trim(),
            asset_kind: it.kind === "asset" ? it.asset_kind : null,
            diseases_or_genes_mentioned: it.mentioned.split(",").map((s) => s.trim()).filter(Boolean),
            what_it_offers: it.what_it_offers.trim() || null,
            how_to_access: null,
            quote: it.quote.trim(),
            nct_id: it.nct_id.trim() || null,
          }))
      : undefined;
    const res = await post<Preview>("/api/contribute/preview", { url: url.trim(), diseaseId: disease || null, contributor: contributor.trim() || undefined, items: manualItems });
    setBusy(null);
    if (!res.ok) {
      setError(res.error);
      if (res.error.code === "llm_unavailable" || res.error.code === "llm_usage_limit") setManual(true);
      return;
    }
    setPreview(res.data);
    setInclude(new Set(res.data.items.filter((it) => it.status === "new" || it.status === "duplicate").map((it) => it.index)));
  };

  const runCommit = async () => {
    if (!preview) return;
    setBusy("commit");
    setError(null);
    const res = await post<CommitResult>("/api/contribute/commit", { preview, contributor: contributor.trim() || undefined, include: [...include].sort((a, b) => a - b) });
    setBusy(null);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setDone(res.data);
    if (res.data.changed && res.data.rebuild.ran && res.data.rebuild.ok) {
      const fresh = await reloadGraph();
      setReloaded(!!fresh);
    }
  };

  const labelOf = (id: string) => idx.nodeById.get(id)?.label ?? id;
  const hrefOf = (id: string) => (id.startsWith("disease:") ? diseaseHref(id) : atlasHref(id));

  return (
    <div className="mx-auto w-full max-w-[920px] px-8 pb-24 pt-10">
      <Header />
      <p className="mt-2 max-w-[700px] text-[15px] leading-relaxed text-ink-3">
        Know a registry, study, biobank, model or patient group the atlas is missing? Paste the page about it. The atlas proposes entries that
        quote the page word for word, and nothing is added until you review and confirm.
      </p>
      {gapQuestion && (
        <p className="mt-4 rounded-lg border border-line bg-subtle px-4 py-3 text-sm text-ink-2">
          <span className="font-medium text-ink">You’re helping answer: </span>
          {gapQuestion}
        </p>
      )}

      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) void runPreview();
        }}
      >
        <label className="block">
          <span className="text-sm font-medium text-ink">Web page</span>
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://… (a page about a registry, study, model or group)"
            className="mt-1.5 h-10 w-full rounded-lg border border-ink-4/70 bg-white px-3 text-sm text-ink focus:border-accent-700 focus:outline-none"
          />
        </label>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-ink">Disease it’s about (optional)</span>
            <select
              value={disease}
              onChange={(e) => setDisease(e.target.value)}
              className="mt-1.5 h-10 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink focus:border-accent-700 focus:outline-none"
            >
              <option value="">Let the page decide</option>
              {diseases.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-ink">Your name or group (optional)</span>
            <input
              value={contributor}
              onChange={(e) => setContributor(e.target.value)}
              placeholder="Shown as the contributor"
              className="mt-1.5 h-10 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink focus:border-accent-700 focus:outline-none"
            />
          </label>
        </div>

        <details open={manual} onToggle={(e) => setManual((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-line px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-ink-2">Enter the items by hand (no AI)</summary>
          <p className="mt-2 text-xs leading-relaxed text-ink-3">
            Copy each sentence exactly as it appears on the page; the atlas checks it word for word, the same way it checks AI output.
          </p>
          <div className="mt-3 space-y-4">
            {items.map((it, i) => (
              <ManualItemEditor
                key={i}
                item={it}
                onChange={(next) => setItems((xs) => xs.map((x, j) => (j === i ? next : x)))}
                onRemove={items.length > 1 ? () => setItems((xs) => xs.filter((_, j) => j !== i)) : undefined}
              />
            ))}
          </div>
          <button type="button" onClick={() => setItems((xs) => [...xs, { ...EMPTY_ITEM }])} className="mt-3 text-sm font-medium text-accent-700 hover:underline">
            Add another item
          </button>
        </details>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy !== null || !url.trim()} className="rounded-md bg-accent-700 px-4 py-2 text-sm font-medium text-white hover:bg-accent-900 disabled:opacity-60">
            {busy === "preview" ? "Reading the page…" : "Read the page"}
          </button>
          <span className="text-xs text-ink-3">
            {manual ? "Checks your items against the page. No AI is used." : "Reads the page and makes one AI call on your ChatGPT plan. Nothing is added yet."}
          </span>
        </div>
      </form>

      {busy === "preview" && <p className="mt-6 text-sm text-ink-3" role="status">Fetching the page and checking every quote. AI reading can take up to 30 seconds.</p>}
      {error && <ErrorPanel error={error} onLogin={() => ai.login(false)} onManual={() => setManual(true)} onRetry={() => void runPreview()} />}

      {preview && !done && (
        <section aria-labelledby="review-h" className="mt-10">
          <h2 id="review-h" className="text-[22px] font-semibold tracking-tight text-ink">
            Review before anything is added
          </h2>
          <p className="mt-1 text-sm text-ink-3">
            <a href={preview.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              {preview.page.title ?? preview.url} ↗
            </a>{" "}
            · read {preview.page.via === "brightdata" ? "through Bright Data" : "directly"}
            {preview.page.from_cache ? " (cached)" : ""} ·{" "}
            {preview.extraction.source === "manual" ? `items entered by hand` : `items proposed by ${preview.extraction.model ?? "AI"}`}
          </p>
          <p className="mt-2 text-sm text-ink-2">
            {preview.summary.new_nodes ?? 0} new entries · {preview.summary.new_sources_for_existing_nodes ?? 0} new sources for existing entries ·{" "}
            {preview.summary.new_edges ?? 0} new links · {preview.summary.rejected ?? 0} rejected · {preview.summary.unlinked ?? 0} need a disease
          </p>
          {preview.previous_contribution && (
            <p className="mt-2 text-xs text-ink-3">This page was added before; adding it again replaces the earlier version.</p>
          )}
          <ul className="mt-5 space-y-3">
            {preview.items.map((it) => (
              <ItemReview
                key={it.index}
                it={it}
                labelOf={labelOf}
                checked={include.has(it.index)}
                onToggle={(on) =>
                  setInclude((s) => {
                    const n = new Set(s);
                    if (on) n.add(it.index);
                    else n.delete(it.index);
                    return n;
                  })
                }
              />
            ))}
          </ul>
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-5">
            <button
              type="button"
              onClick={() => void runCommit()}
              disabled={busy !== null || !preview.can_commit || include.size === 0}
              className="rounded-md bg-accent-700 px-4 py-2 text-sm font-medium text-white hover:bg-accent-900 disabled:opacity-60"
            >
              {busy === "commit" ? "Adding and rebuilding…" : "Add to the atlas"}
            </button>
            <span className="text-xs text-ink-3">
              {preview.can_commit ? `${include.size} item${include.size === 1 ? "" : "s"} selected. Additions are marked “not yet reviewed”.` : "Nothing here can be added: no item was verified and linked."}
            </span>
          </div>
        </section>
      )}

      {done && (
        <section className="mt-10 rounded-lg border border-line px-6 py-5" aria-live="polite">
          <h2 className="text-[17px] font-semibold text-ink">{done.changed ? "Added to the atlas" : "Nothing changed"}</h2>
          <p className="mt-1 text-sm text-ink-2">
            {!done.changed
              ? "This page’s contribution is already in the atlas exactly as previewed."
              : done.rebuild.ran && done.rebuild.ok
                ? reloaded
                  ? "The atlas was rebuilt and this page now shows the new entries. They are marked “Community-contributed · not yet reviewed”."
                  : "The atlas was rebuilt. Reload the page to see the new entries."
                : `Saved to the contributions file; the graph was not rebuilt (${done.rebuild.reason ?? "rebuild skipped"}).`}
          </p>
          {done.written.nodes.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-2">
              {done.written.nodes.slice(0, 8).map((id) => (
                <li key={id}>
                  <Link href={hrefOf(id)} className="inline-block rounded-md border border-line px-2.5 py-1 text-sm text-accent-700 hover:border-accent-500">
                    {labelOf(id)} →
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={() => {
              setDone(null);
              setPreview(null);
              setUrl("");
            }}
            className="mt-4 text-sm font-medium text-accent-700 hover:underline"
          >
            Contribute another page
          </button>
        </section>
      )}
    </div>
  );
}

function ManualItemEditor({ item, onChange, onRemove }: { item: ManualItem; onChange: (i: ManualItem) => void; onRemove?: () => void }) {
  const field = "mt-1 h-9 w-full rounded-md border border-line bg-white px-2.5 text-sm text-ink focus:border-accent-700 focus:outline-none";
  return (
    <div className="rounded-md border border-line-2 bg-subtle/50 px-3 py-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[150px_minmax(0,1fr)_200px]">
        <label className="text-xs text-ink-3">
          Kind
          <select value={item.kind} onChange={(e) => onChange({ ...item, kind: e.target.value as ManualItem["kind"] })} className={field}>
            <option value="asset">Resource</option>
            <option value="patient_org">Patient group</option>
            <option value="study">Registered study (NCT)</option>
          </select>
        </label>
        <label className="text-xs text-ink-3">
          Name
          <input value={item.name} onChange={(e) => onChange({ ...item, name: e.target.value })} className={field} />
        </label>
        {item.kind === "asset" ? (
          <label className="text-xs text-ink-3">
            Type
            <select value={item.asset_kind} onChange={(e) => onChange({ ...item, asset_kind: e.target.value })} className={field}>
              {Object.entries(ASSET_KIND_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        ) : item.kind === "study" ? (
          <label className="text-xs text-ink-3">
            NCT number
            <input value={item.nct_id} onChange={(e) => onChange({ ...item, nct_id: e.target.value })} placeholder="NCT0…" className={field} />
          </label>
        ) : (
          <span />
        )}
      </div>
      <label className="mt-3 block text-xs text-ink-3">
        A sentence from the page, copied exactly
        <textarea value={item.quote} onChange={(e) => onChange({ ...item, quote: e.target.value })} rows={2} className="mt-1 w-full rounded-md border border-line bg-white px-2.5 py-2 text-sm text-ink focus:border-accent-700 focus:outline-none" />
      </label>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="text-xs text-ink-3">
          Diseases or genes the page mentions (comma-separated)
          <input value={item.mentioned} onChange={(e) => onChange({ ...item, mentioned: e.target.value })} className={field} />
        </label>
        <label className="text-xs text-ink-3">
          What it offers (optional)
          <input value={item.what_it_offers} onChange={(e) => onChange({ ...item, what_it_offers: e.target.value })} className={field} />
        </label>
      </div>
      {onRemove && (
        <button type="button" onClick={onRemove} className="mt-2 text-xs text-ink-3 hover:text-ink">
          Remove this item
        </button>
      )}
    </div>
  );
}

function ItemReview({ it, labelOf, checked, onToggle }: { it: PreviewItem; labelOf: (id: string) => string; checked: boolean; onToggle: (on: boolean) => void }) {
  const meta = STATUS_META[it.status] ?? STATUS_META.excluded;
  const selectable = it.status === "new" || it.status === "duplicate" || it.status === "excluded";
  const unreconciled = (it.mentions ?? []).filter((m) => m.status === "unreconciled").map((m) => m.mention);
  return (
    <li className={`rounded-lg border px-5 py-4 ${it.status === "rejected" ? "border-warn-line" : "border-line"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2">
            <span className={`rounded border px-1.5 py-px text-[11px] font-medium ${meta.cls}`}>{meta.label}</span>
            <span className="text-[15px] font-medium text-ink">{it.name}</span>
            <span className="text-xs text-ink-3">
              {it.kind === "asset" && it.asset_kind ? ASSET_KIND_LABEL[it.asset_kind as keyof typeof ASSET_KIND_LABEL] ?? it.asset_kind : it.kind.replace("_", " ")}
            </span>
          </p>
          {it.reason_text && <p className="mt-1 text-sm text-warn-ink">{it.reason_text}</p>}
          {it.status === "unlinked" && <p className="mt-1 text-sm text-ink-2">Pick the disease it’s about above, then read the page again (no extra cost).</p>}
        </div>
        <label className={`flex shrink-0 items-center gap-2 text-sm ${selectable ? "text-ink-2" : "text-ink-4"}`}>
          <input type="checkbox" disabled={!selectable} checked={selectable && checked} onChange={(e) => onToggle(e.target.checked)} className="h-4 w-4 accent-[#1f5a96]" />
          Include
        </label>
      </div>
      {it.quote && (
        <blockquote className="mt-3 border-l-2 border-ink-4 pl-3 text-sm leading-relaxed text-ink-2">
          “{it.quote}”
          <span className={`mt-1 block text-xs font-medium ${it.verification?.ok ? "text-ok" : "text-warn-ink"}`}>
            {it.verification?.ok ? "✓ Verified on the page, word for word" : "✗ Not found on the page"}
          </span>
        </blockquote>
      )}
      {it.duplicate_of && (
        <p className="mt-2 text-sm text-ink-2">
          Adds a source to an existing entry:{" "}
          <Link href={atlasHref(it.duplicate_of.id)} className="font-medium text-accent-700 hover:underline">
            {it.duplicate_of.label}
          </Link>
          {(it.duplicate_of.already_cited || it.duplicate_of.already_cites_url) && <span className="text-ink-3"> (the atlas already cites this page)</span>}
        </p>
      )}
      {(it.diseases?.length ?? 0) > 0 && (
        <p className="mt-2 text-sm text-ink-2">
          <span className="text-ink-3">Links to: </span>
          {it.diseases!.map((d, i) => (
            <span key={d.id}>
              {i > 0 && ", "}
              {d.label} <span className="text-xs text-ink-3">({d.basis === "quote" ? "named in the quote" : d.basis === "page" ? "named on the page" : "your choice"})</span>
            </span>
          ))}
        </p>
      )}
      {unreconciled.length > 0 && <p className="mt-1 text-xs text-ink-3">Not in the atlas yet: {unreconciled.join(", ")}</p>}
      {(it.edges?.length ?? 0) > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-ink-3">
          {it.edges!.map((e) => {
            const [s, , t] = e.id.split("|");
            return (
              <li key={e.id}>
                Proposed link: {labelOf(s)} <span className="text-ink-2">{e.type.replace("_", " ")}</span> {labelOf(t)} · confidence {e.confidence.toFixed(2)} ·{" "}
                {e.status === "adds_evidence" ? "adds evidence to an existing link" : "new"}
              </li>
            );
          })}
        </ul>
      )}
      {(it.warnings?.length ?? 0) > 0 && <p className="mt-1 text-xs text-warn-ink">{it.warnings!.join(" ")}</p>}
    </li>
  );
}

function ErrorPanel({ error, onLogin, onManual, onRetry }: { error: ApiError; onLogin: () => void; onManual: () => void; onRetry: () => void }) {
  const primary = "rounded-md bg-ink px-3.5 py-1.5 text-sm font-medium text-white hover:bg-black";
  let actions: React.ReactNode = null;
  let title = "That didn’t work";
  if (error.code === "llm_unavailable") {
    title = "AI isn’t connected";
    actions = (
      <>
        <ContinueWithChatGPT onClick={onLogin} />
        <button type="button" onClick={onManual} className="text-sm font-medium text-accent-700 hover:underline">
          Enter the items by hand instead
        </button>
      </>
    );
  } else if (error.code === "llm_usage_limit") {
    title = "Usage limit reached";
    actions = (
      <>
        <a href={error.llm?.manage_usage_url ?? MANAGE_USAGE_URL} target="_blank" rel="noopener noreferrer" className={primary}>
          Manage usage
        </a>
        <button type="button" onClick={onManual} className="text-sm font-medium text-accent-700 hover:underline">
          Enter the items by hand instead
        </button>
      </>
    );
  } else if (error.code === "preview_expired" || error.code === "stale_preview" || error.code === "llm_failed" || error.code === "fetch_failed") {
    actions = (
      <button type="button" onClick={onRetry} className={primary}>
        Read the page again
      </button>
    );
  }
  return (
    <div className="mt-6 rounded-lg border border-warn-line bg-warn-bg px-4 py-3.5" role="alert">
      <p className="text-sm font-semibold text-warn-ink">{title}</p>
      <p className="mt-1 text-sm leading-relaxed text-warn-ink">{error.message}</p>
      {actions && <div className="mt-3 flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}
