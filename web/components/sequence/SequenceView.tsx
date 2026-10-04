"use client";

// /sequence: "Check my sequence" for families. A FASTA coding sequence or a VCF file is read and compared
// entirely in the browser (lib/sequence.ts); nothing is uploaded. Each change gets HGVS names, a plain
// consequence, the ClinVar record when the atlas has one, and a one-page report for the doctor.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { explain } from "@/lib/glossary";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { useDerived } from "@/lib/derived";
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";
import {
  CONSEQUENCE_PLAIN,
  checkSequence,
  detectAssembly,
  fileLines,
  geneSpan,
  parseFasta,
  parseVcfLine,
  vcfToChange,
  type Assembly,
  type Change,
  type GeneRef,
  type VcfRecord,
} from "@/lib/sequence";
import { lookupVariant, type VariantRecord, type VariantsData } from "@/lib/variant";

const BASE = "/data/derived/sequences";

interface SeqIndex {
  genes: { gene: string; transcript: string; refseq?: string; cds_length: number }[];
}
interface Examples {
  files: string[];
}

const loadIndex = async (): Promise<{ index: SeqIndex | null; examples: string[]; positions: boolean }> => {
  const a = await loadAvailableOnce();
  if (!a.sequences?.length) return { index: null, examples: [], positions: false };
  const r = await fetch(`${BASE}/index.json`);
  const ex = await fetch(`/data/derived/web/sequence_examples.json`).then((x) => (x.ok ? (x.json() as Promise<Examples>) : { files: [] })).catch(() => ({ files: [] }));
  return { index: r.ok ? ((await r.json()) as SeqIndex) : null, examples: ex.files, positions: !!a.variant_positions };
};

const geneCache = new Map<string, Promise<GeneRef>>();
function loadGene(gene: string): Promise<GeneRef> {
  let p = geneCache.get(gene);
  if (!p) {
    p = fetch(`${BASE}/${gene}.json`).then((r) => {
      if (!r.ok) throw new Error(`No reference for ${gene}`);
      return r.json() as Promise<GeneRef>;
    });
    geneCache.set(gene, p);
  }
  return p;
}

/** variant_positions.json: genomic key -> ClinVar accession(s), from the atlas's stored ClinVar P/LP records. */
interface Positions {
  keys: Record<string, string[]>;
}
let positionsPromise: Promise<Positions | null> | null = null;
function loadPositions(): Promise<Positions | null> {
  positionsPromise ??= fetch("/data/derived/variant_positions.json")
    .then((r) => (r.ok ? (r.json() as Promise<Positions>) : null))
    .catch(() => null);
  return positionsPromise;
}
interface PositionHit {
  accession: string;
  url: string;
  classification: string;
}
/** Exact substitutions by "GRCh38:chr:pos:ref:alt" (or GRCh37); indels by ClinVar SPDI on GRCh38 (0-based, no anchor base). */
function lookupPosition(data: Positions | null, asm: Assembly, v: VcfRecord): PositionHit | null {
  if (!data?.keys) return null;
  let acc = data.keys[`${asm}:${v.chrom}:${v.pos}:${v.ref}:${v.alt}`]?.[0];
  if (!acc && asm === "GRCh38" && v.ref[0] === v.alt[0] && v.ref.length !== v.alt.length)
    acc = data.keys[`SPDI:GRCh38:${v.chrom}:${v.pos}:${v.ref.slice(1)}:${v.alt.slice(1)}`]?.[0];
  if (!acc) return null;
  return { accession: acc, url: `https://www.ncbi.nlm.nih.gov/clinvar/variation/${acc.replace(/^VCV0*/, "")}/`, classification: "Pathogenic or likely pathogenic" };
}

interface Row {
  key: string;
  /** transcript for the printed HGVS, e.g. NM_001032221.6 */
  tx?: string;
  gene: string | null;
  change: Change | null;
  record: VariantRecord | null;
  lookup: "match" | "not_plp" | "no_list" | "outside";
  outsideNote?: string;
  genomic?: { assembly: string; chrom: string; pos: number; ref: string; alt: string };
  position?: PositionHit | null;
}

interface Summary {
  checked: number;
  inGenes: number;
  pathogenic: number;
  assembly: Assembly | null;
  detected: Assembly | null;
}

export function SequenceView() {
  return <WithGraph>{(idx) => <Sequence idx={idx} />}</WithGraph>;
}

function Sequence({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const idxRes = useResource("seq:index", loadIndex);
  const variants = useDerived<VariantsData>("variants");
  const genes = useMemo(() => idxRes?.data?.index?.genes.map((g) => g.gene).sort() ?? [], [idxRes]);
  const [gene, setGene] = useState(() => (params.get("gene") ?? "").toUpperCase());
  const [mode, setMode] = useState<"fasta" | "vcf">("vcf");
  const [fasta, setFasta] = useState("");
  const [asmChoice, setAsmChoice] = useState<"auto" | Assembly>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [source, setSource] = useState<{ label: string; synthetic: boolean } | null>(null);
  const [blastOk, setBlastOk] = useState(false);
  const [geneRef, setGeneRef] = useState<GeneRef | null>(null);
  const vcfInput = useRef<HTMLInputElement>(null);

  const known = gene && genes.includes(gene);
  const vd = variants.status === "ready" ? variants.data : null;

  const describe = (g: string, c: Change): Row => {
    if (!vd || !vd.genes[g]) return { key: `${g}-${c.c}`, gene: g, change: c, record: null, lookup: "no_list", genomic: c.genomic };
    const l = lookupVariant(`${g} ${c.c}`, vd);
    const rec = l.status === "clinvar_match" ? l.matches[0] : null;
    return { key: `${g}-${c.c}`, gene: g, change: c, record: rec, lookup: rec ? "match" : "not_plp", genomic: c.genomic };
  };

  const showResults = () => setTimeout(() => document.getElementById("res-h")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);

  const runFasta = async (text: string, label: string, synthetic: boolean, forGene?: string) => {
    setError(null);
    setRows(null);
    setSummary(null);
    setBusy(true);
    try {
      const g = forGene ?? gene;
      const ref = await loadGene(g);
      setGeneRef(ref);
      const { seq } = parseFasta(text);
      const r = checkSequence(ref, seq);
      if (!r.ok) {
        setError(r.message ?? "We could not compare this sequence.");
        return;
      }
      setSource({ label, synthetic });
      setRows(r.changes.map((c) => ({ ...describe(g, c), tx: ref.refseq ?? ref.transcript })));
      showResults();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runVcf = async (file: File, label: string, synthetic: boolean) => {
    setError(null);
    setRows(null);
    setSummary(null);
    setBusy(true);
    try {
      const refs = await Promise.all(genes.map((g) => loadGene(g).catch(() => null)));
      const positions = idxRes?.data?.positions ? await loadPositions() : null;
      const header: string[] = [];
      let detected: Assembly | null = null;
      let asm: Assembly | null = asmChoice === "auto" ? null : asmChoice;
      let checked = 0;
      let inGenes = 0;
      let pathogenic = 0;
      const out: Row[] = [];
      let spans: { g: GeneRef; chrom: string; start: number; end: number }[] = [];
      for await (const line of fileLines(file)) {
        if (!line) continue;
        if (line.startsWith("##")) {
          header.push(line);
          continue;
        }
        if (line.startsWith("#")) {
          detected = detectAssembly(header);
          asm = asm ?? detected ?? "GRCh38";
          spans = refs
            .filter((g): g is GeneRef => !!g)
            .map((g) => ({ g, s: geneSpan(g, asm!, 1000) }))
            .filter((x): x is { g: GeneRef; s: { chrom: string; start: number; end: number } } => !!x.s)
            .map((x) => ({ g: x.g, ...x.s }));
          continue;
        }
        if (!asm) {
          asm = detected ?? "GRCh38";
          spans = refs.filter((g): g is GeneRef => !!g).flatMap((g) => {
            const s = geneSpan(g, asm!, 1000);
            return s ? [{ g, ...s }] : [];
          });
        }
        for (const v of parseVcfLine(line)) {
          checked++;
          const hitGene = spans.find((s) => s.chrom === v.chrom && v.pos >= s.start && v.pos <= s.end);
          const pos = lookupPosition(positions, asm, v);
          if (hitGene) {
            inGenes++;
            const ch = vcfToChange(hitGene.g, asm, v);
            if (ch && !("outsideCds" in ch)) {
              const row = { ...describe(hitGene.g.gene, ch), position: pos, tx: hitGene.g.refseq ?? hitGene.g.transcript };
              if (row.record && /pathogenic/i.test(row.record.classification) && !/benign|uncertain/i.test(row.record.classification)) pathogenic++;
              else if (pos) pathogenic++;
              out.push(row);
            } else
              out.push({
                key: `${v.chrom}-${v.pos}-${v.alt}`,
                gene: hitGene.g.gene,
                change: null,
                record: null,
                lookup: "outside",
                outsideNote: ch && "outsideCds" in ch ? ch.note : "near the gene but outside its exons",
                genomic: { assembly: asm, chrom: v.chrom, pos: v.pos, ref: v.ref, alt: v.alt },
                position: pos,
              });
          } else if (pos) {
            pathogenic++;
            if (out.length < 300)
              out.push({ key: `${v.chrom}-${v.pos}-${v.alt}`, gene: null, change: null, record: null, lookup: "outside", outsideNote: "outside the genes the atlas maps in depth", genomic: { assembly: asm, chrom: v.chrom, pos: v.pos, ref: v.ref, alt: v.alt }, position: pos });
          }
        }
      }
      setGeneRef(null);
      setSource({ label, synthetic });
      setSummary({ checked, inGenes, pathogenic, assembly: asm, detected });
      setRows(out);
      showResults();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const tryExample = async (name: string) => {
    const r = await fetch(`${BASE}/examples/${encodeURIComponent(name)}`);
    if (!r.ok) return setError("The example could not be loaded.");
    if (/\.vcf(\.gz)?$/i.test(name)) {
      setMode("vcf");
      const blob = await r.blob();
      await runVcf(new File([blob], name), `Synthetic example: ${name}`, true);
    } else {
      const text = await r.text();
      const g = name.split("_")[0].toUpperCase();
      setMode("fasta");
      setGene(g);
      setFasta(text);
      await runFasta(text, `Synthetic example: ${name}`, true, g);
    }
  };

  const examples = idxRes?.data?.examples ?? [];
  const printable = rows?.filter((r) => r.change || r.position) ?? [];

  return (
    <div className="mx-auto w-full max-w-[760px] space-y-8 px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
      <header className="print:hidden">
        <h1 className="text-[28px] font-semibold leading-tight text-ink sm:text-[32px]">Check a DNA sequence or VCF file</h1>
        <p className="mt-3 inline-flex items-center gap-2 rounded-lg border-2 border-ok/50 bg-white px-3 py-2 text-[16px] font-medium text-ink">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="text-ok">
            <rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          Your sequence never leaves this device.
        </p>
        <p className="mt-2 text-[15px] text-ink-2">
          Don’t have one and want to request one?{" "}
          <Link href="/sequence/request" className="font-medium text-accent-700 underline" aria-label="Click here to see how to request a DNA file">
            Click here
          </Link>
        </p>
        <p className="mt-3 text-[16px] leading-relaxed text-ink-2">
          Everything is compared here, in your browser. We list each change, what it does to the protein, and what ClinVar and the atlas say
          about it, so you can show your doctor.
        </p>
        <p className="mt-2 text-sm text-ink-3">This is not a diagnostic test. Only an accredited lab can confirm results.</p>
      </header>

      <section className="space-y-4 rounded-xl border border-line px-4 py-5 print:hidden" aria-label="Your file">
        <div className="flex gap-2" role="tablist" aria-label="What do you have?">
          {(
            [
              ["vcf", "A VCF file (most common)"],
              ["fasta", "A DNA sequence (FASTA)"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`min-h-[44px] rounded-lg border px-3 text-[15px] ${mode === m ? "border-accent-700 bg-accent-50 font-medium text-ink" : "border-line text-ink-2"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "fasta" ? (
          <>
            <label className="block">
              <span className="text-[15px] font-medium text-ink">Gene</span>
              <input
                list="seq-genes"
                value={gene}
                onChange={(e) => setGene(e.target.value.toUpperCase().trim())}
                placeholder="e.g. STXBP1"
                className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px] text-ink focus:border-accent-700 focus:outline-none"
              />
              <datalist id="seq-genes">
                {genes.map((g) => (
                  <option key={g} value={g} />
                ))}
              </datalist>
            </label>
            {gene && genes.length > 0 && !known && (
              <p className="rounded-lg bg-subtle px-3 py-2.5 text-[15px] text-ink-2">
                We can only compare sequences for the {genes.length} genes the atlas maps in depth, and {gene} isn’t one of them yet. If your
                report has a line like “c.1162C&gt;T”, the{" "}
                <Link href={`/variant?q=${encodeURIComponent(gene + " ")}`} className="font-medium text-accent-700 hover:underline">
                  report-line lookup
                </Link>{" "}
                can help.
              </p>
            )}
            <label className="block">
              <span className="text-[15px] font-medium text-ink">Coding sequence (FASTA)</span>
              <textarea
                value={fasta}
                onChange={(e) => setFasta(e.target.value)}
                rows={6}
                spellCheck={false}
                placeholder={">my sequence\nATGGCCCCCATTGGCCTC…"}
                className="mt-1 w-full rounded-lg border border-line px-3 py-2 font-mono text-[13px] text-ink focus:border-accent-700 focus:outline-none"
              />
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <label className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg border border-line px-3 text-[15px] text-ink-2 hover:border-accent-500">
                Choose a file…
                <input
                  type="file"
                  accept=".fa,.fasta,.fna,.txt"
                  className="sr-only"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (f) setFasta(await f.text());
                  }}
                />
              </label>
              <button
                type="button"
                disabled={!known || !fasta.trim() || busy}
                onClick={() => runFasta(fasta, "Your sequence", false)}
                className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900 disabled:opacity-40"
              >
                {busy ? "Comparing…" : "Compare"}
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="block">
              <span className="text-[15px] font-medium text-ink">Genome version</span>
              <select
                value={asmChoice}
                onChange={(e) => setAsmChoice(e.target.value as "auto" | Assembly)}
                className="mt-1 h-11 w-full rounded-lg border border-line bg-white px-3 text-[16px] text-ink sm:w-auto"
              >
                <option value="auto">Detect from the file</option>
                <option value="GRCh38">GRCh38 (hg38)</option>
                <option value="GRCh37">GRCh37 (hg19)</option>
              </select>
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <label className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900">
                {busy ? "Reading…" : "Choose a .vcf or .vcf.gz file"}
                <input
                  ref={vcfInput}
                  type="file"
                  accept=".vcf,.gz,.vcf.gz,text/plain"
                  className="sr-only"
                  disabled={busy}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void runVcf(f, f.name, false);
                    if (vcfInput.current) vcfInput.current.value = "";
                  }}
                />
              </label>
              <span className="text-sm text-ink-3">Large files are fine: they are read in pieces, on this device.</span>
            </div>
          </>
        )}

        {examples.length > 0 && (
          <div className="border-t border-line-2 pt-3">
            <p className="text-sm text-ink-3">Try an example (synthetic data, not a real person):</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {examples
                .filter((e) => (mode === "vcf" ? /\.vcf/i.test(e) : /\.(fa|fasta)$/i.test(e)))
                .map((e) => (
                  <button key={e} type="button" onClick={() => void tryExample(e)} className="rounded-full border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500">
                    {e.replace(/\.(fasta|fa|vcf)$/i, "").replace(/_/g, " ")}
                  </button>
                ))}
            </div>
          </div>
        )}
      </section>

      {error && (
        <p className="rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-[15px] text-warn-ink" role="alert">
          {error}
        </p>
      )}

      {rows && (
        <section aria-labelledby="res-h" className="space-y-4 print:hidden">
          <h2 id="res-h" className="text-[22px] font-semibold text-ink">
            What we found
          </h2>
          {source?.synthetic && <p className="rounded-lg bg-subtle px-3 py-2 text-sm text-ink-2">{source.label}. Synthetic data, not a real person.</p>}
          {summary && (
            <p className="text-[16px] leading-relaxed text-ink">
              We checked {summary.checked.toLocaleString("en-US")} {summary.checked === 1 ? "variant" : "variants"}; {summary.inGenes}{" "}
              {summary.inGenes === 1 ? "falls" : "fall"} in genes the atlas maps in depth; {summary.pathogenic} {summary.pathogenic === 1 ? "is" : "are"} known to
              ClinVar as disease-causing.{" "}
              <span className="text-sm text-ink-3">
                Genome version: {summary.assembly}
                {summary.detected ? " (detected from the file)" : asmChoice === "auto" ? " (could not detect; assumed)" : " (your choice)"}.
              </span>
            </p>
          )}
          {!rows.length && (
            <p className="text-[16px] text-ink-2">
              {summary ? "No changes in the genes the atlas maps in depth, and none matched a ClinVar record we hold." : "No differences from the reference coding sequence."}
            </p>
          )}
          <ul className="space-y-3">
            {rows.map((r) => (
              <ResultCard key={r.key} r={r} idx={idx} />
            ))}
          </ul>
          {printable.length > 0 && (
            <button type="button" onClick={() => window.print()} className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] font-medium text-ink hover:border-accent-500">
              Print for your doctor
            </button>
          )}
          {mode === "fasta" && geneRef && fasta.trim() && (
            <Blast seq={parseFasta(fasta).seq} ok={blastOk} setOk={setBlastOk} />
          )}
        </section>
      )}

      {rows && <PrintReport rows={printable} geneRef={geneRef} summary={summary} source={source} />}
    </div>
  );
}

const STARS: Record<number, string> = { 4: "practice guideline", 3: "reviewed by an expert panel", 2: "several labs agree", 1: "one lab", 0: "no review criteria" };

function vgPlain(idx: GraphIndex, vg: string | null): { label: string; mech: string | null } | null {
  if (!vg) return null;
  const node = idx.nodeById.get(vg);
  const m = (idx.adjacency.get(vg) ?? []).find((n) => n.edge.type === "has_effect" && n.dir === "out");
  const mech = m ? idx.nodeById.get(m.other)?.label ?? null : null;
  return { label: node?.label ?? vg, mech };
}

function clinvarSearch(r: Row): string {
  if (r.change && r.gene) return `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(`${r.gene}[gene] AND "${r.change.c}"`)}`;
  if (r.genomic) {
    const f = r.genomic.assembly === "GRCh37" ? "chrpos37" : "chrpos";
    return `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(`${r.genomic.chrom}[chr] AND ${r.genomic.pos}[${f}]`)}`;
  }
  return "https://www.ncbi.nlm.nih.gov/clinvar/";
}

function ResultCard({ r, idx }: { r: Row; idx: GraphIndex }) {
  const c = r.change;
  const vg = vgPlain(idx, r.record?.variant_group ?? null);
  const mechPlain = vg?.mech ? (explain(vg.mech.split(" (")[0]) ?? vg.mech) : null;
  const disease = r.gene ? idx.nodeById.get(`disease:${r.gene}`) : undefined;
  return (
    <li className="rounded-xl border border-line bg-white px-4 py-4">
      {c ? (
        <>
          <p className="font-mono text-[15px] font-semibold text-ink">
            {r.gene} {c.c}
            {c.p ? <span className="text-ink-2"> → {c.p}</span> : null}
          </p>
          <p className="mt-1 text-[16px] text-ink">{CONSEQUENCE_PLAIN[c.consequence]}</p>
          {c.nearBoundary && c.consequence !== "splice_region" && c.consequence !== "intronic" && (
            <p className="mt-1 text-sm text-ink-3">It is close to an edge where the gene’s pieces are joined (splice region).</p>
          )}
          {c.note && <p className="mt-1 text-sm text-warn-ink">Note: {c.note}.</p>}
        </>
      ) : (
        <>
          <p className="font-mono text-[15px] font-semibold text-ink">
            {r.genomic ? `chr${r.genomic.chrom}:${r.genomic.pos} ${r.genomic.ref}>${r.genomic.alt}` : "Change"}
            {r.gene ? <span className="font-sans text-ink-3"> · {r.gene}</span> : null}
          </p>
          <p className="mt-1 text-[16px] text-ink">This change is {r.outsideNote ?? "outside the genes the atlas maps in depth"}.</p>
        </>
      )}

      <div className="mt-2 space-y-1 text-[15px] text-ink-2">
        {r.record ? (
          <p>
            ClinVar lists this change as <b className="font-medium text-ink">{r.record.classification}</b> ({STARS[r.record.stars] ?? `${r.record.stars} stars`}).{" "}
            <a href={r.record.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              See it in ClinVar ({r.record.accession}) ↗
            </a>
          </p>
        ) : r.position ? (
          <p>
            ClinVar lists this exact change as <b className="font-medium text-ink">{r.position.classification.toLowerCase()}</b>.{" "}
            <a href={r.position.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              {r.position.accession} ↗
            </a>
          </p>
        ) : r.lookup === "outside" ? (
          <p>
            The atlas holds no ClinVar disease-causing record for this exact change. That does not mean it is harmless.{" "}
            <a href={clinvarSearch(r)} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              Search ClinVar ↗
            </a>
          </p>
        ) : r.lookup === "not_plp" ? (
          <p>
            It is not among the changes ClinVar lists as disease-causing for {r.gene}. That does not mean it is harmless; your doctor or lab can say
            more.{" "}
            <a href={clinvarSearch(r)} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              Search ClinVar ↗
            </a>
          </p>
        ) : (
          <p>
            The atlas doesn’t hold ClinVar’s list for this {r.gene ? "gene" : "region"} yet.{" "}
            <a href={clinvarSearch(r)} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
              Search ClinVar for it ↗
            </a>
          </p>
        )}
        {vg && (
          <p>
            In the atlas it belongs to “{vg.label}”.{mechPlain ? ` Changes like this usually work like this: ${mechPlain}` : ""}
          </p>
        )}
        {disease && (
          <p>
            <Link href={diseaseHref(disease.id)} className="text-accent-700 hover:underline">
              What {disease.label} means, in plain words →
            </Link>
          </p>
        )}
      </div>
    </li>
  );
}

/** Opt-in only: a POST to NCBI BLAST. The sequence goes in the request body, never in a URL. */
function Blast({ seq, ok, setOk }: { seq: string; ok: boolean; setOk: (b: boolean) => void }) {
  return (
    <details className="rounded-xl border border-line px-4 py-3">
      <summary className="cursor-pointer text-[15px] font-medium text-ink-2">Compare with NCBI BLAST (optional)</summary>
      <p className="mt-2 text-sm leading-relaxed text-warn-ink">
        This sends your sequence to NCBI (the US National Center for Biotechnology Information) over the internet. Everything else on this page stays
        on your device.
      </p>
      <label className="mt-2 flex items-start gap-2 text-sm text-ink-2">
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="mt-0.5 h-4 w-4" />I understand this sends my sequence to NCBI.
      </label>
      <form action="https://blast.ncbi.nlm.nih.gov/Blast.cgi" method="POST" target="_blank" className="mt-3">
        <input type="hidden" name="CMD" value="Put" />
        <input type="hidden" name="PROGRAM" value="blastn" />
        <input type="hidden" name="MEGABLAST" value="on" />
        <input type="hidden" name="DATABASE" value="refseq_rna" />
        <textarea name="QUERY" value={seq} readOnly hidden />
        <button type="submit" disabled={!ok} className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] text-ink hover:border-accent-500 disabled:opacity-40">
          Send to NCBI BLAST ↗
        </button>
      </form>
    </details>
  );
}

function PrintReport({ rows, geneRef, summary, source }: { rows: Row[]; geneRef: GeneRef | null; summary: Summary | null; source: { label: string; synthetic: boolean } | null }) {
  return (
    <div className="print-sheet" aria-hidden="true">
      <h1 style={{ fontSize: "17pt", fontWeight: 600 }}>DNA changes to discuss with our doctor</h1>
      <p style={{ marginTop: "4pt", fontSize: "10pt" }}>
        {geneRef ? `Gene ${geneRef.gene}, transcript ${geneRef.transcript}${geneRef.refseq ? ` (${geneRef.refseq})` : ""}, ${geneRef.assembly}.` : ""}
        {summary ? ` VCF checked on ${summary.assembly}: ${summary.checked} variants, ${summary.inGenes} in genes mapped in depth.` : ""}
        {source?.synthetic ? " SYNTHETIC EXAMPLE, not a real person." : ""}
      </p>
      <table style={{ marginTop: "10pt", width: "100%", borderCollapse: "collapse", fontSize: "10pt" }}>
        <thead>
          <tr>
            {["Change (HGVS)", "Protein", "Type", "ClinVar", "Atlas"].map((h) => (
              <th key={h} style={{ textAlign: "left", borderBottom: "1px solid #000", padding: "3pt" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td style={{ padding: "3pt", borderBottom: "1px solid #ccc" }}>
                {r.change ? `${r.tx ?? r.gene}(${r.gene}):${r.change.c}` : r.genomic ? `${r.genomic.assembly} chr${r.genomic.chrom}:g.${r.genomic.pos}${r.genomic.ref}>${r.genomic.alt}` : ""}
              </td>
              <td style={{ padding: "3pt", borderBottom: "1px solid #ccc" }}>{r.change?.p ?? ""}</td>
              <td style={{ padding: "3pt", borderBottom: "1px solid #ccc" }}>{r.change?.consequence.replace(/_/g, " ") ?? "outside mapped genes"}</td>
              <td style={{ padding: "3pt", borderBottom: "1px solid #ccc" }}>
                {r.record ? `${r.record.classification} (${r.record.accession}) ${r.record.url}` : r.position ? `${r.position.classification} (${r.position.accession}) ${r.position.url}` : "not in the atlas’s ClinVar list"}
              </td>
              <td style={{ padding: "3pt", borderBottom: "1px solid #ccc" }}>{r.record?.variant_group ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ marginTop: "12pt", fontSize: "9pt" }}>
        This is not a diagnostic test. Only an accredited lab can confirm results. Compared in the browser with the Rare Disease Atlas; reference coding
        sequences from Ensembl (MANE Select); ClinVar pathogenic / likely pathogenic records as stored by the atlas.
      </p>
    </div>
  );
}
