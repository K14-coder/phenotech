// "Check my sequence": everything runs in the browser. Aligns a pasted coding sequence (FASTA) against the
// reference CDS of a deep gene (data/derived/sequences/<GENE>.json) with a banded global alignment, and
// maps VCF records onto the same transcripts using the exon table. Output: HGVS c. and p. and a
// consequence class, ready for lib/variant.ts lookups. Not a diagnostic tool.

export interface Exon {
  number: number;
  chrom: string;
  start: number;
  end: number;
  strand: number;
  cds_start: number | null;
  cds_end: number | null;
  coding_genomic_start?: number;
  coding_genomic_end?: number;
}

export interface GeneRef {
  gene: string;
  assembly: string;
  transcript: string;
  refseq?: string;
  strand: number;
  chrom: string;
  cds: string;
  protein: string;
  exons: Exon[];
  grch37?: { available: boolean; transcript?: string; chrom?: string; strand?: number; exons?: Exon[] };
}

export type Consequence = "missense" | "nonsense" | "frameshift" | "synonymous" | "inframe_deletion" | "inframe_insertion" | "start_lost" | "stop_lost" | "splice_region" | "intronic" | "other";

export interface Change {
  /** HGVS coding notation, e.g. c.1162C>T */
  c: string;
  /** HGVS protein notation, e.g. p.Arg388Ter (null when not computable) */
  p: string | null;
  consequence: Consequence;
  /** first CDS position involved */
  pos: number;
  /** within 3 bases of an exon boundary inside the CDS */
  nearBoundary: boolean;
  note?: string;
  /** VCF origin, when the change came from a VCF line */
  genomic?: { assembly: string; chrom: string; pos: number; ref: string; alt: string };
}

const AA3: Record<string, string> = {
  A: "Ala", R: "Arg", N: "Asn", D: "Asp", C: "Cys", E: "Glu", Q: "Gln", G: "Gly", H: "His", I: "Ile",
  L: "Leu", K: "Lys", M: "Met", F: "Phe", P: "Pro", S: "Ser", T: "Thr", W: "Trp", Y: "Tyr", V: "Val", "*": "Ter",
};
const CODON: Record<string, string> = {};
{
  const b = "TCAG";
  const aa = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG";
  let i = 0;
  for (const x of b) for (const y of b) for (const z of b) CODON[x + y + z] = aa[i++];
}
export const translateCodon = (c: string) => CODON[c] ?? "X";
const COMP: Record<string, string> = { A: "T", T: "A", C: "G", G: "C", N: "N" };
export const revcomp = (s: string) => s.split("").reverse().map((c) => COMP[c] ?? "N").join("");

// ---------- FASTA ----------

export function parseFasta(text: string): { header: string | null; seq: string } {
  const lines = text.replace(/\r/g, "").split("\n");
  let header: string | null = null;
  const parts: string[] = [];
  for (const l of lines) {
    if (l.startsWith(">")) {
      if (header === null) header = l.slice(1).trim();
      else if (parts.length) break; // first record only
      continue;
    }
    parts.push(l);
  }
  return { header, seq: parts.join("").toUpperCase().replace(/[^ACGTN]/g, "") };
}

// ---------- banded global alignment ----------

/**
 * Global alignment of `q` to `r` within a band around the diagonal (match 0, mismatch 1, gap 1). Returns
 * aligned pairs as arrays of the same length with "-" for gaps, or null if the sequences differ by more
 * than the band allows.
 */
export function bandedAlign(r: string, q: string, band = 60): { ra: string[]; qa: string[] } | null {
  const n = r.length;
  const m = q.length;
  if (Math.abs(n - m) > band) return null;
  const W = 2 * band + 1;
  const INF = 1e9;
  const score = new Float64Array((n + 1) * W).fill(INF);
  const back = new Uint8Array((n + 1) * W); // 1 diag, 2 up (gap in q), 3 left (gap in r)
  const at = (i: number, j: number) => i * W + (j - i + band);
  const inBand = (i: number, j: number) => j >= 0 && j <= m && Math.abs(j - i) <= band;
  score[at(0, 0)] = 0;
  for (let j = 1; j <= Math.min(m, band); j++) {
    score[at(0, j)] = j;
    back[at(0, j)] = 3;
  }
  for (let i = 1; i <= n; i++) {
    const lo = Math.max(0, i - band);
    const hi = Math.min(m, i + band);
    for (let j = lo; j <= hi; j++) {
      let best = INF;
      let dir = 0;
      if (j > 0 && inBand(i - 1, j - 1)) {
        const s = score[at(i - 1, j - 1)] + (r[i - 1] === q[j - 1] ? 0 : 1);
        if (s < best) {
          best = s;
          dir = 1;
        }
      }
      if (inBand(i - 1, j)) {
        const s = score[at(i - 1, j)] + 1;
        if (s < best) {
          best = s;
          dir = 2;
        }
      }
      if (j > 0 && inBand(i, j - 1)) {
        const s = score[at(i, j - 1)] + 1;
        if (s < best) {
          best = s;
          dir = 3;
        }
      }
      score[at(i, j)] = best;
      back[at(i, j)] = dir;
    }
  }
  if (!inBand(n, m) || score[at(n, m)] >= INF) return null;
  const ra: string[] = [];
  const qa: string[] = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    const d = back[at(i, j)];
    if (d === 1) {
      ra.push(r[--i]);
      qa.push(q[--j]);
    } else if (d === 2) {
      ra.push(r[--i]);
      qa.push("-");
    } else {
      ra.push("-");
      qa.push(q[--j]);
    }
  }
  return { ra: ra.reverse(), qa: qa.reverse() };
}

/** Trim a query to the reference CDS when it carries flanking sequence (finds the reference start and end). */
export function trimToCds(ref: string, q: string): string {
  if (q.length <= ref.length + 20) return q;
  const head = ref.slice(0, 24);
  const tail = ref.slice(-24);
  const a = q.indexOf(head);
  const b = q.lastIndexOf(tail);
  if (a >= 0 && b > a) return q.slice(a, b + tail.length);
  return q;
}

// ---------- differences -> HGVS ----------

function boundaries(g: GeneRef): number[] {
  return g.exons.filter((e) => e.cds_end != null).map((e) => e.cds_end as number);
}

function nearBoundary(g: GeneRef, pos: number): boolean {
  return boundaries(g).some((b) => b < g.cds.length && (Math.abs(pos - b) <= 2 || Math.abs(pos - (b + 1)) <= 2));
}

const aa3 = (a: string) => AA3[a] ?? "Xaa";

/** Protein effect of a coding change, by translating the reference and the changed CDS. */
function proteinEffect(g: GeneRef, mutCds: string, pos: number, delta: number): { p: string | null; consequence: Consequence } {
  const ref = g.cds;
  const codonIdx = Math.floor((pos - 1) / 3);
  const aaPos = codonIdx + 1;
  const refAa = translateCodon(ref.slice(codonIdx * 3, codonIdx * 3 + 3));
  if (delta % 3 !== 0) {
    // frameshift: first changed amino acid, and the new stop if one appears
    let k = codonIdx;
    while (k * 3 + 3 <= mutCds.length && translateCodon(mutCds.slice(k * 3, k * 3 + 3)) === translateCodon(ref.slice(k * 3, k * 3 + 3))) k++;
    const from = translateCodon(ref.slice(k * 3, k * 3 + 3));
    const to = translateCodon(mutCds.slice(k * 3, k * 3 + 3));
    let stop = 0;
    for (let s = k; s * 3 + 3 <= mutCds.length; s++) {
      stop++;
      if (translateCodon(mutCds.slice(s * 3, s * 3 + 3)) === "*") break;
    }
    if (aaPos === 1 && codonIdx === 0) return { p: "p.Met1?", consequence: "start_lost" };
    return { p: `p.${aa3(from)}${k + 1}${aa3(to)}fsTer${stop}`, consequence: "frameshift" };
  }
  if (delta === 0) {
    const mutAa = translateCodon(mutCds.slice(codonIdx * 3, codonIdx * 3 + 3));
    if (aaPos === 1 && mutAa !== "M") return { p: "p.Met1?", consequence: "start_lost" };
    if (mutAa === refAa) return { p: `p.${aa3(refAa)}${aaPos}=`, consequence: "synonymous" };
    if (mutAa === "*") return { p: `p.${aa3(refAa)}${aaPos}Ter`, consequence: "nonsense" };
    if (refAa === "*") return { p: `p.Ter${aaPos}${aa3(mutAa)}ext*?`, consequence: "stop_lost" };
    return { p: `p.${aa3(refAa)}${aaPos}${aa3(mutAa)}`, consequence: "missense" };
  }
  return { p: delta < 0 ? `p.${aa3(refAa)}${aaPos}del` : `p.${aa3(refAa)}${aaPos}ins`, consequence: delta < 0 ? "inframe_deletion" : "inframe_insertion" };
}

/** Shift an indel to its most 3' position in the reference (HGVS 3' rule). */
function shift3(ref: string, start: number, seq: string, isDel: boolean): number {
  // start is 0-based index of the first deleted base, or of the base after which seq is inserted (+1)
  let s = start;
  const L = seq.length;
  if (isDel) {
    while (s + L < ref.length && ref[s] === ref[s + L]) s++;
  } else {
    let unit = seq;
    while (s < ref.length && ref[s] === unit[0]) {
      unit = unit.slice(1) + unit[0];
      s++;
    }
  }
  return s;
}

export function diffsFromAlignment(g: GeneRef, ra: string[], qa: string[], mutCds: string): Change[] {
  const out: Change[] = [];
  let rpos = 0; // reference bases consumed
  let k = 0;
  while (k < ra.length) {
    if (ra[k] !== "-" && qa[k] !== "-") {
      if (ra[k] !== qa[k] && qa[k] !== "N") {
        const pos = rpos + 1;
        const eff = proteinEffect(g, g.cds.slice(0, pos - 1) + qa[k] + g.cds.slice(pos), pos, 0);
        out.push({ c: `c.${pos}${ra[k]}>${qa[k]}`, ...eff, pos, nearBoundary: nearBoundary(g, pos) });
      }
      rpos++;
      k++;
    } else if (qa[k] === "-") {
      let del = "";
      while (k < ra.length && qa[k] === "-") {
        del += ra[k];
        k++;
        rpos++;
      }
      const s0 = shift3(g.cds, rpos - del.length, del, true);
      const a = s0 + 1;
      const b = s0 + del.length;
      const delSeq = g.cds.slice(s0, s0 + del.length);
      const eff = proteinEffect(g, g.cds.slice(0, s0) + g.cds.slice(s0 + del.length), a, -del.length);
      out.push({ c: del.length === 1 ? `c.${a}del` : `c.${a}_${b}del`, ...eff, pos: a, nearBoundary: nearBoundary(g, a), note: `deletes ${delSeq}` });
    } else {
      let ins = "";
      while (k < ra.length && ra[k] === "-") {
        ins += qa[k];
        k++;
      }
      const s0 = shift3(g.cds, rpos, ins, false); // insertion before index s0
      let seq = ins;
      // rotate the inserted sequence to match the shift
      for (let x = rpos; x < s0; x++) seq = seq.slice(1) + seq[0];
      const isDup = s0 >= seq.length && g.cds.slice(s0 - seq.length, s0) === seq;
      const eff = proteinEffect(g, g.cds.slice(0, s0) + seq + g.cds.slice(s0), s0 + 1, seq.length);
      const c = isDup ? (seq.length === 1 ? `c.${s0}dup` : `c.${s0 - seq.length + 1}_${s0}dup`) : `c.${s0}_${s0 + 1}ins${seq}`;
      out.push({ c, ...eff, pos: Math.max(1, s0), nearBoundary: nearBoundary(g, s0) });
    }
  }
  void mutCds;
  return out;
}

export interface AlignResult {
  ok: boolean;
  message?: string;
  changes: Change[];
  identity: number;
  queryLength: number;
}

export function checkSequence(g: GeneRef, rawQuery: string): AlignResult {
  let q = trimToCds(g.cds, rawQuery);
  if (q.length < 30) return { ok: false, message: "The sequence is too short to compare. Paste the gene’s coding sequence (it starts with ATG).", changes: [], identity: 0, queryLength: q.length };
  // a reverse-complemented paste still works
  const fwd = g.cds.slice(0, 20);
  if (!q.includes(fwd.slice(0, 12)) && revcomp(q).includes(fwd.slice(0, 12))) q = revcomp(q);
  const al = bandedAlign(g.cds, q, Math.min(200, Math.max(60, Math.abs(g.cds.length - q.length) + 30)));
  if (!al) return { ok: false, message: `This sequence is very different in length from the ${g.gene} coding sequence (${g.cds.length} letters). Is it the right gene, and only the coding part?`, changes: [], identity: 0, queryLength: q.length };
  let same = 0;
  for (let i = 0; i < al.ra.length; i++) if (al.ra[i] === al.qa[i]) same++;
  const identity = same / Math.max(g.cds.length, q.length);
  if (identity < 0.9) return { ok: false, message: `Only ${Math.round(identity * 100)}% of this sequence matches ${g.gene}. It may be a different gene or a different part of it.`, changes: [], identity, queryLength: q.length };
  return { ok: true, changes: diffsFromAlignment(g, al.ra, al.qa, q), identity, queryLength: q.length };
}

// ---------- VCF ----------

export type Assembly = "GRCh37" | "GRCh38";

export interface VcfRecord {
  chrom: string;
  pos: number;
  id: string;
  ref: string;
  alt: string;
}

const CHR1 = { GRCh38: 248956422, GRCh37: 249250621 };

/** Guess the assembly from ##reference / ##contig header lines (null when unclear). */
export function detectAssembly(headerLines: string[]): Assembly | null {
  for (const l of headerLines) {
    const low = l.toLowerCase();
    if (low.startsWith("##reference") || low.startsWith("##assembly")) {
      if (/grch38|hg38|hs38/.test(low)) return "GRCh38";
      if (/grch37|hg19|b37|hs37/.test(low)) return "GRCh37";
    }
    const m = l.match(/^##contig=<ID=(?:chr)?1,.*length=(\d+)/i);
    if (m) {
      const len = Number(m[1]);
      if (len === CHR1.GRCh38) return "GRCh38";
      if (len === CHR1.GRCh37) return "GRCh37";
    }
    const asm = l.match(/^##contig=<.*assembly=([^,>]+)/i)?.[1]?.toLowerCase();
    if (asm) {
      if (/38/.test(asm)) return "GRCh38";
      if (/37|19/.test(asm)) return "GRCh37";
    }
  }
  return null;
}

/** Streams lines from a File (plain or gzip) without loading the whole text into memory. */
export async function* fileLines(file: File): AsyncGenerator<string> {
  let stream: ReadableStream<Uint8Array> = file.stream();
  const gz = file.name.toLowerCase().endsWith(".gz");
  if (gz) {
    if (typeof DecompressionStream === "undefined") throw new Error("This browser cannot open .gz files. Unzip the file first and choose the .vcf.");
    stream = stream.pipeThrough(new DecompressionStream("gzip") as unknown as TransformStream<Uint8Array, Uint8Array>);
  }
  const reader = stream.pipeThrough(new TextDecoderStream() as unknown as TransformStream<Uint8Array, string>).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      yield buf.slice(0, nl).replace(/\r$/, "");
      buf = buf.slice(nl + 1);
    }
  }
  if (buf) yield buf;
}

export function parseVcfLine(line: string): VcfRecord[] {
  const f = line.split("\t");
  if (f.length < 5) return [];
  const chrom = f[0].replace(/^chr/i, "");
  const pos = Number(f[1]);
  if (!Number.isFinite(pos)) return [];
  return f[4]
    .split(",")
    .filter((a) => /^[ACGTN]+$/i.test(a))
    .map((alt) => ({ chrom, pos, id: f[2], ref: f[3].toUpperCase(), alt: alt.toUpperCase() }));
}

/** Exons and strand of a gene for an assembly (GRCh38 top level, GRCh37 under .grch37). */
export function exonsFor(g: GeneRef, asm: Assembly): { exons: Exon[]; strand: number; chrom: string } | null {
  if (asm === "GRCh38") return { exons: g.exons, strand: g.strand, chrom: g.chrom };
  if (g.grch37?.available && g.grch37.exons) return { exons: g.grch37.exons, strand: g.grch37.strand ?? g.strand, chrom: g.grch37.chrom ?? g.chrom };
  return null;
}

export function geneSpan(g: GeneRef, asm: Assembly, pad = 50): { chrom: string; start: number; end: number } | null {
  const ex = exonsFor(g, asm);
  if (!ex) return null;
  return { chrom: ex.chrom, start: Math.min(...ex.exons.map((e) => e.start)) - pad, end: Math.max(...ex.exons.map((e) => e.end)) + pad };
}

/** Coding position of a genomic coordinate: "123", "123+5", "124-3", or null outside the CDS region. */
function cPosOf(exons: Exon[], strand: number, gpos: number): { c: string; inCds: boolean; cds?: number } | null {
  const coding = exons.filter((e) => e.cds_start != null && e.coding_genomic_start != null && e.coding_genomic_end != null);
  for (const e of coding) {
    if (gpos >= e.coding_genomic_start! && gpos <= e.coding_genomic_end!) {
      const cds = strand === 1 ? e.cds_start! + (gpos - e.coding_genomic_start!) : e.cds_start! + (e.coding_genomic_end! - gpos);
      return { c: String(cds), inCds: true, cds };
    }
  }
  // intronic, near the closest coding exon edge (within 50 bases)
  let best: { c: string; d: number } | null = null;
  for (const e of coding) {
    const s = e.coding_genomic_start!;
    const t = e.coding_genomic_end!;
    const dLow = s - gpos; // before the exon on the genome
    const dHigh = gpos - t; // after the exon
    if (dLow > 0 && dLow <= 50) {
      const c = strand === 1 ? `${e.cds_start}-${dLow}` : `${e.cds_end}+${dLow}`;
      if (!best || dLow < best.d) best = { c, d: dLow };
    }
    if (dHigh > 0 && dHigh <= 50) {
      const c = strand === 1 ? `${e.cds_end}+${dHigh}` : `${e.cds_start}-${dHigh}`;
      if (!best || dHigh < best.d) best = { c, d: dHigh };
    }
  }
  return best ? { c: best.c, inCds: false } : null;
}

/** Maps one VCF record onto the gene's transcript. Returns null when it is outside the gene region. */
export function vcfToChange(g: GeneRef, asm: Assembly, v: VcfRecord): Change | { outsideCds: true; note: string } | null {
  const ex = exonsFor(g, asm);
  if (!ex || v.chrom !== ex.chrom) return null;
  const genomic = { assembly: asm, chrom: v.chrom, pos: v.pos, ref: v.ref, alt: v.alt };
  const strand = ex.strand;
  const comp = (s: string) => (strand === 1 ? s : revcomp(s));
  if (v.ref.length === 1 && v.alt.length === 1) {
    const p = cPosOf(ex.exons, strand, v.pos);
    if (!p) return { outsideCds: true, note: "in the gene region but away from the coding exons" };
    const refB = comp(v.ref);
    const altB = comp(v.alt);
    if (!p.inCds) {
      const off = Number(p.c.split(/[+-]/)[1]);
      return { c: `c.${p.c}${refB}>${altB}`, p: null, consequence: off <= 8 ? "splice_region" : "intronic", pos: Number(p.c.split(/[+-]/)[0]), nearBoundary: true, genomic, note: off <= 2 ? "at the splice site" : undefined };
    }
    const pos = p.cds!;
    const note = g.cds[pos - 1] !== refB ? `the file’s reference base (${refB}) does not match the ${asm} transcript (${g.cds[pos - 1]}); check the assembly` : undefined;
    const eff = proteinEffect(g, g.cds.slice(0, pos - 1) + altB + g.cds.slice(pos), pos, 0);
    return { c: `c.${pos}${refB}>${altB}`, ...eff, pos, nearBoundary: nearBoundary(g, pos), genomic, note };
  }
  // simple indels: VCF shares the first (padding) base
  if (v.ref[0] !== v.alt[0]) return { outsideCds: true, note: "a complex change; ask the lab for its HGVS name" };
  const delta = v.alt.length - v.ref.length;
  if (delta < 0) {
    const first = v.pos + 1;
    const last = v.pos + v.ref.length - 1;
    const a = cPosOf(ex.exons, strand, strand === 1 ? first : last);
    const b = cPosOf(ex.exons, strand, strand === 1 ? last : first);
    if (!a?.inCds || !b?.inCds) return { outsideCds: true, note: "a deletion outside the coding sequence" };
    const s = Math.min(a.cds!, b.cds!);
    const e = Math.max(a.cds!, b.cds!);
    const eff = proteinEffect(g, g.cds.slice(0, s - 1) + g.cds.slice(e), s, delta);
    return { c: s === e ? `c.${s}del` : `c.${s}_${e}del`, ...eff, pos: s, nearBoundary: nearBoundary(g, s), genomic };
  }
  const anchor = cPosOf(ex.exons, strand, v.pos);
  if (!anchor?.inCds) return { outsideCds: true, note: "an insertion outside the coding sequence" };
  const insSeq = comp(v.alt.slice(1));
  // on the minus strand the insertion sits before the anchor base in coding order
  const after = strand === 1 ? anchor.cds! : anchor.cds! - 1;
  const eff = proteinEffect(g, g.cds.slice(0, after) + insSeq + g.cds.slice(after), after + 1, delta);
  const isDup = g.cds.slice(after - insSeq.length, after) === insSeq;
  return {
    c: isDup ? (insSeq.length === 1 ? `c.${after}dup` : `c.${after - insSeq.length + 1}_${after}dup`) : `c.${after}_${after + 1}ins${insSeq}`,
    ...eff,
    pos: after,
    nearBoundary: nearBoundary(g, after),
    genomic,
  };
}

export const CONSEQUENCE_PLAIN: Record<Consequence, string> = {
  missense: "Changes one building block of the protein.",
  nonsense: "Puts a stop signal in the instructions, so the protein is cut short.",
  frameshift: "Shifts how the rest of the instructions are read; the protein is usually cut short.",
  synonymous: "Does not change the protein (a silent change).",
  inframe_deletion: "Removes building blocks from the protein without shifting the rest.",
  inframe_insertion: "Adds building blocks to the protein without shifting the rest.",
  start_lost: "Changes the start signal, so the protein may not be made.",
  stop_lost: "Removes the stop signal, so the protein may be made too long.",
  splice_region: "Sits at an edge where the gene’s pieces are joined; it may change how they are joined.",
  intronic: "Sits between the coding pieces of the gene; usually less likely to matter.",
  other: "A change whose effect we cannot work out here.",
};
