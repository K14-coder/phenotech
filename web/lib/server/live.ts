// Live checks behind the daily cron: for a followed disease, ask ClinicalTrials.gov (API v2) for
// recruiting / not-yet-recruiting studies and NIH RePORTER for recently funded projects on its genes.
// Matching follows the precision rules of data/derived/scale/README.md (pipeline/scale/build_trials.py),
// ported in a compact form:
//  - disease name or synonym as a whole phrase in the study's conditions, keywords or title; no
//    hyphen-glued hits ("Crigler-Najjar" is not "Najjar syndrome"), no gene-context hits ("... gene"),
//    no digit-free abbreviations, no generic single words;
//  - gene symbol, case-sensitive, with a gene context (bare symbol, or mutation / variant / related /
//    deficiency ... within 3 words), never in oncology or common-disease studies, never in drug,
//    biomarker or SNP contexts, never when the study spells the symbol out as an acronym; stoplisted
//    symbols are skipped. Gene matches are worded "mentions <GENE>".
// RePORTER results keep only the project title, organisation and the public project page. Names of
// investigators are never requested.
import { readFile } from "node:fs/promises";
import path from "node:path";

export interface DiseaseProfile {
  id: string;
  name: string;
  terms: string[];
  genes: string[];
}

export interface LiveItem {
  key: string;
  kind: "trial" | "grant";
  title: string;
  url: string;
  meta: string;
}

const ONCO =
  /cancer|carcinoma|tumou?r|neoplas|leuka?emia|lymphoma|melanoma|sarcoma|glioma|blastoma|myeloma|malignan|metasta|oncolog|myelodysplast|myeloproliferat|nsclc|adenocarcinoma|polyposis|paraganglioma|pheochromocytoma|mesothelioma|seminoma|histiocytosis/i;
const COMMON = [
  "alzheimer", "parkinson", "diabetes", "obesity", "hypertension", "coronary", "myocardial infarction", "heart failure", "stroke",
  "atrial fibrillation", "depress", "schizophren", "bipolar", "hiv", "hepatitis", "covid", "sars-cov", "influenza", "malaria",
  "tuberculosis", "asthma", "copd", "chronic kidney disease", "osteoarthritis", "rheumatoid", "psoriasis", "sepsis", "pain",
  "smoking", "alcohol", "opioid", "atherosclero", "dyslipid", "hypercholesterol", "cardiovascular", "infertility", "pregnan",
  "healthy", "migraine", "osteoporosis", "glaucoma", "macular degeneration", "chronic obstructive", "emphysema",
  "multiple sclerosis", "pulmonary fibrosis", "thrombosis", "bleeding", "iron deficiency", "kidney transplant",
];
const SYMBOL_STOP = new Set(
  `PAH APP ACE REN AGT CRP ALB EPO INS GH1 IGF1 PTH OXT AVP GCG TNF LEP AMH CGA NPPA NPPB MPO PRL TPO CETP PCSK9 HMGCR NPC1L1 DPP4
ANGPTL3 APOC3 LPA APOE APOB MTOR VEGFA EGFR ERBB2 HLA CD4 CD8 CD19 CD20 TSH FSHB LHB CYP2D6 CYP2C19 CYP2C9 CYP3A5 VKORC1 SLCO1B1
TPMT NUDT15 DPYD UGT1A1 IL6 IL2 IL1B IL10 IFNG TGFB1 MTHFR F2 F5 ESR1 AR PGR GNRH1 KISS1 ACTH POMC GHRH SST INSR GLP1R GIPR SLC5A2
AQP4 MOG PLP1 MBP ABO RHD KEL FUT2 ADA ATM CAD SDS PDF NRL MAX ASL CBS GLA HEX TAT TTR PIGA ACAN TF VWF GPI NHS IHH ATR DCC HBB MCC
REST CAT CLOCK SMS PHB NOS CPS PKD POR ARC PDS IPS DMP FAP MSS CAP RNA DNA`.split(/\s+/),
);
const GENERIC_SINGLE = new Set(
  `obesity epilepsy deafness anemia anaemia asthma autism dementia hypertension diabetes cataract cataracts glaucoma myopia
infertility lymphoma leukemia ataxia dystonia neuropathy cardiomyopathy microcephaly macrocephaly hydrocephalus scoliosis
osteoporosis hypothyroidism hyperthyroidism neutropenia thrombocytopenia cholestasis proteinuria hematuria ichthyosis albinism
craniosynostosis polydactyly syndactyly nephropathy myopathy retinopathy encephalopathy leukodystrophy dwarfism hypogonadism
hypoparathyroidism infection arrhythmia thrombophilia hemophilia coloboma anophthalmia microphthalmia nystagmus strabismus
achromatopsia amyloidosis lipodystrophy porphyria hyperinsulinism hypoglycemia hyperammonemia hypercalcemia hypocalcemia
hypokalemia hyperkalemia hypophosphatemia hyperphosphatemia osteopetrosis neurodegeneration`.split(/\s+/),
);
const GENE_CTX =
  /^(gene|genes|mutation|mutations|mutated|variant|variants|pathogenic|germline|related|associated|deficiency|deficient|syndrome|disorder|disorders|encephalopathy|disease|carrier|carriers|gof|lof|haploinsufficiency|biallelic|heterozygous|homozygous|mosaic|alteration|alterations|positive|negative|linked|dee|epilepsy|ndd|patients|individuals|children|loss|gain|function|defect|defects|deletion|duplication|spectrum|dystrophy|myopathy|cardiomyopathy|retinopathy|neuropathy|ataxia|dependent|rd)$/i;
const NON_GENE_CTX = /inhibit|antagon|agonist|antibod|blocker|modulator|polymorphism|\bsnps?\b|\brs\d+|level|levels|expression|serum|plasma|biomarker|staining|immunohisto|vaccine/i;

const fold = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "");
const norm = (s: string) => fold(s).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const isAbbrev = (s: string) => !s.trim().includes(" ") && s.length <= 10 && [...s].filter((c) => /[A-Z0-9]/.test(c)).length >= 0.6 * s.length;

/** OMIM-style names: "#123456 NAME;;ALT" -> "NAME"; "Dystrophy, Duchenne" -> also "Duchenne Dystrophy". */
function cleanName(s: string): string[] {
  const base = s.replace(/^[#%*+^]?\d{6}\s+/, "").split(";;")[0].trim();
  const parts = base.split(",").map((p) => p.trim()).filter(Boolean);
  const out = [base];
  if (parts.length === 2) out.push(`${parts[1]} ${parts[0]}`);
  return out;
}

export function usableTerms(names: string[], genes: Set<string>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of names.flatMap(cleanName)) {
    const n = raw.trim();
    if (!n || /susceptibility|\{/i.test(n)) continue;
    if (isAbbrev(n) && (!/\d/.test(n) || n.length < 4 || [...n].filter((c) => /[A-Za-z]/.test(c)).length < 2 || genes.has(n))) continue;
    const k = norm(n);
    const toks = k.split(" ");
    if (k.length < 5) continue;
    if (toks.length === 1 && (k.length < 7 || GENERIC_SINGLE.has(k))) continue;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(n);
  }
  return out;
}

export function usableGenes(genes: string[]): string[] {
  if (genes.length >= 10) return []; // umbrella entities: gene matches would be meaningless
  return genes.filter((g) => g.length >= 3 && /^[A-Z0-9-]+$/.test(g) && !SYMBOL_STOP.has(g) && !g.startsWith("HLA-"));
}

/** Whole-phrase match of `term` in `text`, not glued to a preceding word by a hyphen, not followed by a gene context. */
export function nameIn(term: string, text: string): boolean {
  const toks = norm(term).split(" ");
  const re = new RegExp(`(^|[^A-Za-z0-9-])(${toks.map(esc).join("[\\s\\-'’,.]*")})(?![A-Za-z0-9])`, "gi");
  const o = fold(text);
  for (const m of o.matchAll(re)) {
    const end = (m.index ?? 0) + m[0].length;
    if (/^[\s-]*(mutated|gene\b|genes\b|mutation|carrier|variant|protein|kinase|inhibit)/i.test(o.slice(end, end + 14))) continue;
    return true;
  }
  return false;
}

function acronymDefined(sym: string, texts: string[]): boolean {
  const letters = [...sym].filter((c) => /[A-Za-z]/.test(c)).map((c) => c.toLowerCase());
  if (letters.length < 3 || letters.length !== [...sym].filter((c) => !/\d/.test(c)).length) return false;
  for (const t of texts) {
    const words = t.match(/[A-Za-z][A-Za-z']*/g) ?? [];
    for (let i = 0; i + letters.length <= words.length; i++) {
      const w = words.slice(i, i + letters.length);
      if (w.every((x, j) => x[0].toLowerCase() === letters[j]) && w.filter((x) => x[0] === x[0].toUpperCase()).length >= letters.length - 1) return true;
    }
  }
  return false;
}

/** Strict gene match (trials): symbol with a gene context in `text`. */
export function geneIn(sym: string, text: string, allTexts: string[]): boolean {
  if (NON_GENE_CTX.test(text)) return false;
  const tokRe = /[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*/g;
  let found = false;
  for (const m of text.matchAll(tokRe)) {
    const tok = m[0];
    const parts = new Set([tok, ...tok.split(/[-./]/)]);
    if (!parts.has(sym)) continue;
    if (/^anti-/i.test(tok) || new RegExp(`${esc(sym)}-\\d{2,}`).test(tok)) continue;
    const after = text.slice((m.index ?? 0) + tok.length, (m.index ?? 0) + tok.length + 14).toLowerCase();
    if (/^( inhibitor|-inhibit|i | antagonist| agonist| antibod)/.test(after)) continue;
    found = true;
  }
  if (!found) return false;
  const bare = new RegExp(`^\\s*(the\\s+)?${esc(sym)}(\\s+gene)?\\s*$`, "i").test(text);
  const words = text.match(/[A-Za-z0-9']+/g) ?? [];
  const idx = words.flatMap((w, i) => (w === sym || w.split(/[-./]/).includes(sym) ? [i] : []));
  const near = idx.some((i) => words.slice(Math.max(0, i - 3), i + 4).some((w) => w !== sym && GENE_CTX.test(w)));
  if (!(bare || near)) return false;
  return !acronymDefined(sym, allTexts);
}

// ---------- disease profiles from the synced data ----------

async function publicJson<T>(rel: string, base: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(process.cwd(), "public", rel), "utf8")) as T;
  } catch {
    try {
      const r = await fetch(`${base}/${rel}`, { cache: "no-store" });
      return r.ok ? ((await r.json()) as T) : null;
    } catch {
      return null;
    }
  }
}

interface GraphNode {
  id: string;
  type: string;
  label: string;
  synonyms?: string[];
  attrs?: { gene?: string; genes?: string[] };
}
interface IndexFile {
  f: string[];
  rows: unknown[][];
}

export async function loadProfiles(ids: string[], base: string): Promise<Map<string, DiseaseProfile>> {
  const out = new Map<string, DiseaseProfile>();
  const atlas = ids.filter((d) => d.startsWith("disease:"));
  const global = new Set(ids.filter((d) => !d.startsWith("disease:")));
  if (atlas.length) {
    const g = await publicJson<{ nodes: GraphNode[] }>("data/graph.json", base);
    for (const n of g?.nodes ?? []) {
      if (n.type !== "disease" || !atlas.includes(n.id)) continue;
      const genes = n.attrs?.genes ?? [n.attrs?.gene ?? n.id.replace(/^disease:/, "")];
      out.set(n.id, { id: n.id, name: n.label, terms: [], genes: usableGenes(genes) });
      out.get(n.id)!.terms = usableTerms([n.label.replace(/\s*\(.*\)$/, ""), ...(n.synonyms ?? [])], new Set(genes));
    }
  }
  if (global.size) {
    for (const file of ["data/derived/global/index.json", "data/derived/global/index_extra.json"]) {
      const j = await publicJson<IndexFile>(file, base);
      if (!j) continue;
      const F = Object.fromEntries(j.f.map((k, i) => [k, i]));
      for (const r of j.rows) {
        const id = String(r[F.id]);
        if (!global.has(id) || out.has(id)) continue;
        const genes = String(r[F.genes] ?? "").split(",").filter(Boolean);
        const name = cleanName(String(r[F.name]))[0];
        out.set(id, { id, name, terms: usableTerms([String(r[F.name]), ...((r[F.syn] as string[]) ?? [])], new Set(genes)), genes: usableGenes(genes) });
      }
    }
  }
  return out;
}

// ---------- live sources ----------

const UA = { "User-Agent": "tasukeru/0.1 (followed-disease alerts)" };
const status = (s?: string) => (s ?? "").toLowerCase().replace(/_/g, " ");

interface CtStudy {
  protocolSection: {
    identificationModule: { nctId: string; briefTitle: string };
    statusModule?: { overallStatus?: string };
    sponsorCollaboratorsModule?: { leadSponsor?: { name?: string } };
    conditionsModule?: { conditions?: string[]; keywords?: string[] };
  };
}

/** Recruiting / not-yet-recruiting studies for a disease, after the precision filter. One request. */
export async function liveTrials(p: DiseaseProfile, timeoutMs = 8000): Promise<LiveItem[] | null> {
  const terms = [...p.terms.slice(0, 6), ...p.genes.slice(0, 3)];
  if (!terms.length) return [];
  const q = terms.map((t) => `"${t.replace(/"/g, "")}"`).join(" OR ");
  const url =
    "https://clinicaltrials.gov/api/v2/studies?" +
    new URLSearchParams({
      "query.term": q,
      "filter.overallStatus": "RECRUITING,NOT_YET_RECRUITING",
      pageSize: "100",
      fields: "NCTId,BriefTitle,Condition,Keyword,OverallStatus,LeadSponsorName",
    });
  try {
    const r = await fetch(url, { headers: UA, signal: AbortSignal.timeout(timeoutMs), cache: "no-store" });
    if (!r.ok) return null;
    const j = (await r.json()) as { studies?: CtStudy[] };
    const out: LiveItem[] = [];
    for (const s of j.studies ?? []) {
      const ps = s.protocolSection;
      const conds = ps.conditionsModule?.conditions ?? [];
      const kws = ps.conditionsModule?.keywords ?? [];
      const title = ps.identificationModule.briefTitle;
      const fields = [...conds, ...kws, title];
      const byName = p.terms.some((t) => fields.some((f) => nameIn(t, f)));
      let viaGene: string | null = null;
      if (!byName) {
        const condText = conds.join(" ; ").toLowerCase();
        const onco = ONCO.test(condText) || ONCO.test(title);
        const common = COMMON.some((c) => condText.includes(c));
        if (!onco && !common) viaGene = p.genes.find((g) => fields.some((f) => geneIn(g, f, fields))) ?? null;
      }
      if (!byName && !viaGene) continue;
      const nct = ps.identificationModule.nctId;
      out.push({
        key: `trial-${nct}`,
        kind: "trial",
        title,
        url: `https://clinicaltrials.gov/study/${nct}`,
        meta: [status(ps.statusModule?.overallStatus), ps.sponsorCollaboratorsModule?.leadSponsor?.name, viaGene ? `mentions ${viaGene}` : null].filter(Boolean).join(" · "),
      });
    }
    return out;
  } catch {
    return null;
  }
}

interface ReporterProject {
  appl_id: number;
  project_num?: string;
  project_title?: string;
  fiscal_year?: number;
  pref_terms?: string;
  organization?: { org_name?: string };
}

const titleCase = (s: string) => s.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(Of|And|The|At|For|In)\b/g, (w) => w.toLowerCase());

/** NIH RePORTER projects (this and last fiscal year) naming one of the disease's genes. One request. */
export async function liveGrants(p: DiseaseProfile, now = new Date(), timeoutMs = 8000): Promise<LiveItem[] | null> {
  const genes = p.genes.slice(0, 5);
  if (!genes.length) return [];
  const y = now.getUTCFullYear();
  try {
    const r = await fetch("https://api.reporter.nih.gov/v2/projects/search", {
      method: "POST",
      headers: { ...UA, "Content-Type": "application/json" },
      body: JSON.stringify({
        criteria: { fiscal_years: [y - 1, y], advanced_text_search: { operator: "or", search_field: "projecttitle,terms", search_text: genes.join(" ") } },
        // only what is shown: no investigator names or contact details are requested
        include_fields: ["ApplId", "ProjectNum", "ProjectTitle", "FiscalYear", "Organization", "PrefTerms"],
        limit: 50,
      }),
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
    if (!r.ok) return null;
    const j = (await r.json()) as { results?: ReporterProject[] };
    const byCore = new Map<string, LiveItem>();
    for (const x of j.results ?? []) {
      const text = `${x.project_title ?? ""} ; ${x.pref_terms ?? ""}`;
      const gene = genes.find((g) => new RegExp(`(^|[^A-Za-z0-9])${esc(g)}([^A-Za-z0-9]|$)`).test(text));
      if (!gene || !x.project_title) continue;
      const core = x.project_num?.match(/^\d?([A-Z]\d{2}[A-Z]{2}\d{6})/)?.[1] ?? String(x.appl_id);
      if (byCore.has(core)) continue;
      byCore.set(core, {
        key: `grant-${core}`,
        kind: "grant",
        title: x.project_title,
        url: `https://reporter.nih.gov/project-details/${x.appl_id}`,
        meta: [x.organization?.org_name ? titleCase(x.organization.org_name) : null, x.fiscal_year ? `NIH, fiscal year ${x.fiscal_year}` : "NIH", `mentions ${gene}`].filter(Boolean).join(" · "),
      });
    }
    return [...byCore.values()];
  } catch {
    return null;
  }
}
