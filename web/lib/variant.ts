// Variant lookup: a port of pipeline/derive/hgvs.py (spec: data/derived/variant_lookup_spec.md).
// Self-contained on purpose (no imports), so `node scripts/test-variants.mjs` can run it directly
// and check all cases in data/derived/variant_test_cases.json.

export interface VariantsData {
  meta: { scope_note: string; url_template?: string; stars?: string; generated?: string };
  fields: string[];
  transcript_to_gene: Record<string, string>;
  variant_groups: string[];
  genes: Record<
    string,
    {
      n: number;
      by_consequence: Record<string, number>;
      null_like_share?: number;
      recurrent_residues?: { residue: string; alleles: string[] }[];
      most_reported?: { p: string; accession: string; n_submissions: number }[];
      variants: unknown[][];
    }
  >;
  index: Record<string, number[]>;
}

export interface VariantRecord {
  gene: string;
  accession: string;
  url: string;
  hgvs: string;
  p: string | null;
  protein_change: string | null;
  consequence: string;
  classification: string;
  stars: number;
  n_submissions: number;
  variant_group: string | null;
}

export interface ParsedQuery {
  raw: string;
  gene: string | null;
  gene_source: string | null;
  transcript: string | null;
  c: string | null;
  p: string | null;
  cnv: boolean;
  non_slice_gene: string | null;
}

export type LookupStatus = "clinvar_match" | "not_in_clinvar_plp" | "not_found_no_gene" | "gene_not_in_atlas" | "unparsed";

export interface LookupResult {
  query: ParsedQuery;
  status: LookupStatus;
  match_on?: "c" | "p" | "isoform";
  matches: VariantRecord[];
  fallback: { consequence: string; certainty: string; note: string; variant_group: string | null } | null;
  warnings: string[];
}

const AA3: Record<string, string> = {
  Ala: "A", Arg: "R", Asn: "N", Asp: "D", Cys: "C", Gln: "Q", Glu: "E", Gly: "G", His: "H", Ile: "I", Leu: "L", Lys: "K",
  Met: "M", Phe: "F", Pro: "P", Ser: "S", Thr: "T", Trp: "W", Tyr: "Y", Val: "V", Sec: "U", Pyl: "O", Ter: "*",
};
const AA1 = new Set("ACDEFGHIKLMNPQRSTVWYUO".split(""));
const VG_SLUG: Record<string, string> = {
  nonsense: "truncating",
  frameshift: "truncating",
  start_lost: "truncating",
  splice: "splice",
  missense: "missense",
  cnv_single: "whole-gene-deletion",
  cnv_multi: "contiguous-gene-deletion",
};

const AA3_ALT = "(?:" + Object.keys(AA3).join("|") + ")";
const RE_TX = /\b(N[MC]_\d+(?:\.\d+)?)\b/i;
const RE_TX_GENE = /\b(N[MC]_\d+(?:\.\d+)?)\s*\(\s*([A-Za-z0-9-]+)\s*\)/i;
const RE_C = /\bc\.\s*((?:[-*]?\d+(?:[+-]\d+)?)(?:_(?:[-*]?\d+(?:[+-]\d+)?))?)\s*([ACGTacgt]>[ACGTacgt]|delins[ACGTacgt]+|del[ACGTacgt]*|dup[ACGTacgt]*|ins[ACGTacgt]+|inv)/;
const RE_P3 = new RegExp(
  "(?:\\b[pP]\\.\\s*\\(?\\s*|\\b)(" + AA3_ALT + ")(\\d+)(?:_(" + AA3_ALT + ")(\\d+))?" +
    "(" + AA3_ALT + "|\\*|X|=|\\?|fs[A-Za-z*]*\\d*|del(?:ins[A-Za-z*]+)?|dup|ins[A-Za-z*]+|[A-Z][a-z]{2}fs\\S*)",
  "gi",
);
const RE_P1 =
  /(?:\b[pP]\.\s*\(?\s*|(?<![A-Za-z0-9.]))([ACDEFGHIKLMNPQRSTVWY])(\d+)(?:_([ACDEFGHIKLMNPQRSTVWY])(\d+))?([ACDEFGHIKLMNPQRSTVWY*X=?](?:fs\*?\d*)?|fs\*?\d*|del(?:ins[A-Z*]+)?|dup|ins[A-Z*]+)(?![A-Za-z0-9])/g;
const RE_CNV =
  /(copy[- ]number|\bcnv\b|micro(?:deletion|duplication)|\bdeletion\b|\bduplication\b|\bdel\(|\bdup\(|\)x[0-4]\b|\bx[0134]\b|whole[- ]gene|exons?\s*\d+(?:\s*[-–]\s*\d+)?\s*(?:del|dup))/i;
const RE_GENE_TOKEN = /\b([A-Z][A-Z0-9]{1,9}(?:-AS1)?)\b/g;

function aa(code: string): string {
  if (code === "*" || code === "X" || code === "x") return "*";
  if (code.length === 3) return AA3[code[0].toUpperCase() + code.slice(1).toLowerCase()] ?? "";
  return AA1.has(code.toUpperCase()) ? code.toUpperCase() : "";
}

export function normalizeC(text: string): string | null {
  const m = RE_C.exec(text || "");
  if (!m) return null;
  const pos = m[1];
  let change = m[2];
  if (change.includes(">")) change = change.toUpperCase();
  else {
    const kind = /^(delins|del|dup|ins|inv)/.exec(change)![1];
    change = kind + change.slice(kind.length).toUpperCase();
  }
  return `c.${pos}${change}`;
}

export function normalizeP(text: string): string | null {
  text = text || "";
  for (const m of text.matchAll(RE_P3)) {
    const [, a1, pos, a2, pos2, r] = m;
    const ref = aa(a1);
    if (!ref) continue;
    const rng = a2 ? `_${aa(a2)}${pos2}` : "";
    if (/fs/i.test(r)) return `${ref}${pos}fs`;
    const lower = r.toLowerCase();
    const aaList = (s: string) => (s.match(new RegExp(AA3_ALT + "|\\*", "gi")) ?? []).map(aa).join("");
    if (lower.startsWith("delins")) return `${ref}${pos}${rng}delins${aaList(r.slice(6))}`;
    if (lower.startsWith("del")) return `${ref}${pos}${rng}del`;
    if (lower.startsWith("dup")) return `${ref}${pos}${rng}dup`;
    if (lower.startsWith("ins")) return `${ref}${pos}${rng}ins${aaList(r.slice(3))}`;
    if (r === "=" || r === "?") return `${ref}${pos}${r}`;
    const alt = aa(r);
    if (alt) return `${ref}${pos}${alt}`;
  }
  for (const m of text.matchAll(RE_P1)) {
    const [, ref, pos, a2, pos2, rest] = m;
    const rng = a2 ? `_${a2}${pos2}` : "";
    if (rest.includes("fs")) return `${ref}${pos}fs`;
    if (rest.startsWith("del") || rest.startsWith("dup") || rest.startsWith("ins")) return `${ref}${pos}${rng}${rest}`;
    if (rest === "=" || rest === "?") return `${ref}${pos}${rest}`;
    return `${ref}${pos}${aa(rest[0])}`;
  }
  return null;
}

type Cls = [consequence: string, certainty: string, note: string];

export function classifyP(p: string | null): Cls | null {
  if (!p) return null;
  if (p.endsWith("fs")) return ["frameshift", "certain", "frameshift in the protein notation"];
  if (/^M1(\?|[A-Z*])$/.test(p) || p.endsWith("?")) return ["other", "likely", "start-codon change (start-lost); grouped with truncating variants"];
  if (/(delins|del|dup|ins)/.test(p)) {
    if (p.endsWith("*") || /ins[A-Z]*\*/.test(p)) return ["nonsense", "likely", "in-frame change that introduces a stop codon"];
    return ["inframe_indel", "certain", "in-frame deletion/insertion/duplication"];
  }
  if (p.endsWith("=")) return ["synonymous", "certain", "no amino-acid change"];
  if (p.endsWith("*")) return ["nonsense", "certain", "premature stop codon"];
  if (/^[A-Z]\d+[A-Z]$/.test(p)) return ["missense", "certain", "single amino-acid substitution"];
  return ["other", "unknown", "protein notation not recognised"];
}

function posParts(pos: string): [number, number, string] {
  const m = /^([-*]?)(\d+)(?:([+-])(\d+))?$/.exec(pos)!;
  const offset = m[4] ? (m[3] === "+" ? Number(m[4]) : -Number(m[4])) : 0;
  return [Number(m[2]), offset, m[1]];
}

export function classifyC(c: string | null): Cls | null {
  if (!c) return null;
  const m = /^c\.([^A-Za-z_]+?)(?:_([^A-Za-z]+?))?([ACGT]>[ACGT]|delins[ACGT]+|del[ACGT]*|dup[ACGT]*|ins[ACGT]+|inv)$/.exec(c);
  if (!m) return ["other", "unknown", "c. notation not recognised"];
  const [, p1, p2, change] = m;
  const parts = [posParts(p1), ...(p2 ? [posParts(p2)] : [])];
  const offsets = parts.map((x) => x[1]);
  const prefixes = parts.map((x) => x[2]);
  const utr = (pre: string) => pre === "-" || pre === "*";
  if (prefixes.some(utr) && prefixes.every(utr)) return ["other", "likely", "untranslated region (UTR) change"];
  if (offsets.some((o) => o !== 0 && (Math.abs(o) === 1 || Math.abs(o) === 2))) return ["splice", "likely", "canonical splice site (intron position +/-1 or 2)"];
  if (offsets.some((o) => o !== 0)) {
    if (offsets.filter((o) => o !== 0).every((o) => Math.abs(o) <= 10)) return ["splice", "possible", "intronic change near an exon boundary; may affect splicing"];
    return ["other", "unknown", "deep intronic change; effect cannot be read from the notation"];
  }
  if (change.includes(">")) {
    const base = parts[0][0];
    if ((base === 1 || base === 2 || base === 3) && !p2) return ["other", "likely", "start-codon change (start-lost); grouped with truncating variants"];
    return ["other", "unknown", "exonic single-letter change: missense, nonsense or silent cannot be told from the c. notation alone (look for the p. notation)"];
  }
  const start = parts[0][0];
  const end = p2 ? parts[1][0] : start;
  const span = end - start + 1;
  let net: number;
  if (change.startsWith("delins")) net = change.length - 6 - span;
  else if (change.startsWith("del")) net = -span;
  else if (change.startsWith("dup")) net = span;
  else if (change.startsWith("ins")) net = change.length - 3;
  else return ["other", "unknown", "inversion"];
  const signed = `${net >= 0 ? "+" : ""}${net}`;
  if (net % 3 === 0) return ["inframe_indel", "likely", `net length change ${signed} bases keeps the reading frame`];
  return ["frameshift", "likely", `net length change ${signed} bases shifts the reading frame`];
}

export function parseQuery(text: string, genes: Set<string>, tx2gene: Record<string, string>): ParsedQuery {
  text = (text || "").trim();
  const out: ParsedQuery = { raw: text, gene: null, gene_source: null, transcript: null, c: null, p: null, cnv: false, non_slice_gene: null };
  const m = RE_TX_GENE.exec(text);
  if (m) {
    out.transcript = m[1].toUpperCase();
    out.gene = m[2].toUpperCase();
    out.gene_source = "transcript(gene)";
  } else {
    const mt = RE_TX.exec(text);
    if (mt) {
      out.transcript = mt[1].toUpperCase();
      const base = out.transcript.split(".")[0];
      if (tx2gene[base]) {
        out.gene = tx2gene[base];
        out.gene_source = "transcript";
      }
    }
  }
  if (!out.gene) {
    for (const t of text.toUpperCase().matchAll(RE_GENE_TOKEN)) {
      if (genes.has(t[1])) {
        out.gene = t[1];
        out.gene_source = "symbol";
        break;
      }
    }
  }
  if (!out.gene) {
    for (const t of text.matchAll(RE_GENE_TOKEN)) {
      const tok = t[1];
      if (normalizeP(tok) || ["CNV", "DEL", "DUP", "MANE", "HGVS", "ACMG", "VUS", "NM", "NC"].includes(tok)) continue;
      if (/^[ACGT]+$/.test(tok)) continue;
      out.non_slice_gene = tok;
      break;
    }
  } else if (!genes.has(out.gene)) {
    out.non_slice_gene = out.gene;
    out.gene = null;
  }
  out.c = normalizeC(text);
  out.p =
    normalizeP(text) ||
    normalizeP(text.replace(/(?<![A-Za-z0-9.])([a-z])(\d+)([a-z*])(?![A-Za-z0-9])/g, (s) => s.toUpperCase()));
  out.cnv = RE_CNV.test(text) && !out.c && !out.p;
  return out;
}

export function lookupVariant(text: string, data: VariantsData): LookupResult {
  const genes = new Set(Object.keys(data.genes));
  const q = parseQuery(text, genes, data.transcript_to_gene);
  const res: LookupResult = { query: q, status: "unparsed", matches: [], warnings: [], fallback: null };
  if (q.non_slice_gene && !q.gene) {
    res.status = "gene_not_in_atlas";
    res.warnings.push(`${q.non_slice_gene} is not one of the ${genes.size} genes in this atlas slice.`);
    return res;
  }
  if (!(q.c || q.p || q.cnv)) {
    res.status = "unparsed";
    return res;
  }
  const searchGenes = q.gene ? [q.gene] : [...genes].sort();
  const idx = data.index;
  const rows = (gene: string, ids: number[]): VariantRecord[] =>
    ids.map((i) => {
      const row = data.genes[gene].variants[i];
      const rec = Object.fromEntries(data.fields.map((f, k) => [f, row[k]])) as Omit<VariantRecord, "gene">;
      return { ...rec, gene };
    });

  let hits: VariantRecord[] = [];
  let how: LookupResult["match_on"];
  for (const gene of searchGenes) {
    const k = `c:${gene}:${q.c}`;
    if (q.c && idx[k]) {
      hits = hits.concat(rows(gene, idx[k]));
      how = "c";
    }
  }
  if (!hits.length && q.p) {
    for (const gene of searchGenes) {
      const k = `p:${gene}:${q.p}`;
      if (idx[k]) {
        hits = hits.concat(rows(gene, idx[k]));
        how = "p";
      }
    }
  }
  if (!hits.length && q.p) {
    for (const gene of searchGenes) {
      const k = `iso:${gene}:${q.p}`;
      if (idx[k]) {
        hits = hits.concat(rows(gene, idx[k]));
        how = "isoform";
      }
    }
  }
  if (hits.length) {
    res.status = "clinvar_match";
    res.match_on = how;
    res.matches = hits;
    if (how === "isoform") res.warnings.push("Matched only through another isoform's amino-acid numbering in ClinVar; confirm the transcript with your genetic counsellor.");
    if (!q.gene) res.warnings.push("No gene was given; the gene was inferred from the match.");
    if (q.c && q.p && how === "c" && !hits.some((h) => h.p === q.p)) {
      res.warnings.push("The protein change you typed does not match the one ClinVar lists for this c. change; check the report.");
    }
    if (q.transcript) {
      const txRec = new Set(hits.filter((h) => h.hgvs.startsWith("N")).map((h) => h.hgvs.split("(")[0]));
      const bases = new Set([...txRec].map((t) => t.split(".")[0]));
      if (txRec.size && !bases.has(q.transcript.split(".")[0])) {
        res.warnings.push(
          `Your report uses ${q.transcript}; ClinVar's record uses ${[...txRec].sort().join(", ")}. Numbering can differ between transcripts, so confirm the match.`,
        );
      }
    }
    return res;
  }

  // fallback: classify the typed notation by pattern
  let cls = q.p ? classifyP(q.p) : null;
  if ((!cls || cls[1] === "unknown") && q.c) cls = classifyC(q.c);
  if (!cls && q.cnv) cls = ["cnv", "likely", "copy-number / whole-gene or exon-level change"];
  const [consequence, certainty, note] = cls!;
  let slug: string | undefined = VG_SLUG[note.includes("start-lost") ? "start_lost" : consequence];
  if (consequence === "cnv") slug = "whole-gene-deletion";
  let vg: string | null = null;
  if (q.gene && slug && data.variant_groups.includes(`vg:${q.gene}:${slug}`)) vg = `vg:${q.gene}:${slug}`;
  res.status = q.gene ? "not_in_clinvar_plp" : "not_found_no_gene";
  res.fallback = { consequence, certainty, note, variant_group: vg };
  res.warnings.push(
    "Not among ClinVar's pathogenic/likely-pathogenic records for this gene (it may be a VUS, benign, new, or written differently). The type shown is read from the notation only.",
  );
  return res;
}

/** Cheap check for the global search: does this look like a variant (c./p./transcript/CNV wording)? */
export function looksLikeVariant(text: string): boolean {
  const t = (text || "").trim();
  if (t.length < 4) return false;
  if (RE_TX.test(t) || RE_C.test(t)) return true;
  if (/\bp\.\s*\(?[A-Za-z]{1,3}\d+/i.test(t)) return true;
  // "STXBP1 R388X", "R406H", "Arg388Ter": a protein change token
  if (/(?<![A-Za-z0-9.])[A-Z]\d{1,4}(?:[A-Z*=]|fs|del|dup|ins)(?![A-Za-z0-9])/.test(t.replace(/(?<![A-Za-z0-9.])([a-z])(\d+)([a-z*])(?![A-Za-z0-9])/g, (s) => s.toUpperCase()))) return true;
  if (new RegExp("\\b" + AA3_ALT + "\\d+(" + AA3_ALT + "|\\*|X|=|fs|del|dup|ins)", "i").test(t)) return true;
  return /\b[A-Z][A-Z0-9]{1,9}\b.*\b(whole[- ]gene|deletion|duplication|microdeletion|cnv)\b/i.test(t);
}
