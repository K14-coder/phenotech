import type {
  AssetKind,
  AtlasEdge,
  AtlasNode,
  EvidenceLevel,
  EvidenceStudyType,
  NodeType,
  RelationType,
} from "./types";

export const TYPE_LABEL: Record<NodeType, { one: string; many: string; hint: string }> = {
  disease: { one: "Disease", many: "Diseases", hint: "A condition, grouped by the gene that causes it" },
  gene: { one: "Gene", many: "Genes", hint: "Instructions for making one protein" },
  variant_group: { one: "Gene change type", many: "Gene change types", hint: "A group of similar changes in one gene" },
  mechanism: { one: "Mechanism", many: "Mechanisms", hint: "What goes wrong in the body, or the process involved" },
  phenotype: { one: "Symptom", many: "Symptoms", hint: "A feature you can observe, like seizures" },
  patient_org: { one: "Patient group", many: "Patient groups", hint: "Families and advocates organised around a condition" },
  asset: { one: "Resource", many: "Resources", hint: "Registries, studies, models and tools already built" },
  study: { one: "Study or trial", many: "Studies and trials", hint: "Registered clinical studies" },
  therapy: { one: "Therapy", many: "Therapies", hint: "Treatments, from idea to approved" },
  publication: { one: "Publication", many: "Publications", hint: "Papers that support connections" },
  researcher: { one: "Researcher", many: "Researchers", hint: "Professional public information only" },
  grant: { one: "Grant", many: "Grants", hint: "Research funding" },
};

export const EVIDENCE_LEVELS: EvidenceLevel[] = [
  "clinical",
  "curated",
  "experimental",
  "observational",
  "inferred",
  "hypothesis",
];

export const EVIDENCE_LEVEL_META: Record<EvidenceLevel, { label: string; short: string; legend: string }> = {
  clinical: { label: "Clinical", short: "Clinical", legend: "Shown in patients in a clinical study or trial." },
  curated: { label: "Curated database", short: "Curated", legend: "Recorded by expert curators in a public database such as OMIM or HPO." },
  experimental: { label: "Experimental", short: "Experimental", legend: "Shown in lab experiments with cells or animal models." },
  observational: { label: "Case reports", short: "Case reports", legend: "Observed in individual patients or small groups of patients." },
  inferred: { label: "Inferred by atlas", short: "Inferred", legend: "Computed by the atlas from shared features. No source states it directly." },
  hypothesis: { label: "Hypothesis", short: "Hypothesis", legend: "An untested idea worth checking. Never presented as fact." },
};

export function isEvidenceBacked(level: EvidenceLevel) {
  return level !== "inferred" && level !== "hypothesis";
}

export function confidenceWord(c: number): string {
  if (c >= 0.9) return "Very strong";
  if (c >= 0.7) return "Strong";
  if (c >= 0.5) return "Moderate";
  if (c >= 0.3) return "Weak";
  return "Speculative";
}

export const CONFIDENCE_RUBRIC: { min: number; text: string }[] = [
  { min: 0.9, text: "Curated database record plus a publication, or a clinical trial result" },
  { min: 0.7, text: "Two or more independent publications, or one curated database record" },
  { min: 0.5, text: "A single publication, or lab evidence only" },
  { min: 0.3, text: "Inferred by the atlas from shared features" },
  { min: 0, text: "An untested hypothesis, drawn dotted and never presented as fact" },
];

export function rubricFor(c: number) {
  return CONFIDENCE_RUBRIC.find((r) => c >= r.min)!.text;
}

/** Relation phrasing used in sentences: "<source> <verb> <target>". */
const RELATION_VERB: Record<RelationType, string> = {
  causes: "causes",
  variant_in: "are changes in",
  has_effect: "lead to",
  participates_in: "takes part in",
  driven_by: "is driven by",
  has_phenotype: "can include",
  shares_mechanism: "shares a mechanism with",
  similar_phenotype: "has similar symptoms to",
  serves: "supports families with",
  maintains: "runs",
  covers: "includes people with",
  studies: "studies",
  tests: "tests",
  targets: "aims at",
  developed_for: "is being developed for",
  works_on: "works on",
  authored: "wrote",
  funds: "funds",
  about: "is about",
  candidate_for: "might be worth testing for",
};

export const RELATION_NAME: Record<RelationType, string> = {
  causes: "Causes",
  variant_in: "Gene change in",
  has_effect: "Has effect",
  participates_in: "Takes part in",
  driven_by: "Driven by",
  has_phenotype: "Has symptom",
  shares_mechanism: "Shares mechanism",
  similar_phenotype: "Similar symptoms",
  serves: "Serves",
  maintains: "Maintains",
  covers: "Covers",
  studies: "Studies",
  tests: "Tests",
  targets: "Targets",
  developed_for: "Developed for",
  works_on: "Works on",
  authored: "Authored",
  funds: "Funds",
  about: "About",
  candidate_for: "Hypothesis: worth testing",
};

export function relationVerb(e: AtlasEdge): string {
  return RELATION_VERB[e.type] ?? e.label ?? e.type.replace(/_/g, " ");
}

export function relationName(t: RelationType | string): string {
  return RELATION_NAME[t as RelationType] ?? String(t).replace(/_/g, " ");
}

/** Display name that makes gene vs disease obvious ("STXBP1 gene"). */
export function nodeName(n: AtlasNode | undefined, fallbackId = ""): string {
  if (!n) return fallbackId;
  if (n.type === "gene") return `${n.label} gene`;
  return n.label;
}

/** Lower-cases generic nouns mid-sentence ("Seizure" -> "seizure") but keeps names and acronyms ("SNARE", "STXBP1"). */
function midSentence(n: AtlasNode | undefined, fallback: string): string {
  const name = nodeName(n, fallback);
  const generic = n && (n.type === "mechanism" || n.type === "phenotype" || n.type === "therapy");
  if (generic && /^[A-Z][a-z]/.test(name)) return name[0].toLowerCase() + name.slice(1);
  return name;
}

export function relationSentence(e: AtlasEdge, source?: AtlasNode, target?: AtlasNode): string {
  return `${nodeName(source, e.source)} ${relationVerb(e)} ${midSentence(target, e.target)}`;
}

export const ASSET_KIND_LABEL: Record<AssetKind, string> = {
  registry: "Patient registry",
  natural_history_study: "Natural history study",
  biobank: "Biobank",
  animal_model: "Animal model",
  cell_model: "Cell model",
  outcome_measure: "Outcome measure",
  assay: "Lab assay",
  trial_design: "Trial design",
  research_network: "Research network",
  funding_program: "Funding program",
  data_platform: "Data platform",
};

export const STUDY_TYPE_LABEL: Record<EvidenceStudyType, string> = {
  clinical_trial: "Clinical trial",
  case_report: "Case report",
  case_series: "Case series",
  cohort: "Cohort study",
  functional_study: "Lab study",
  animal_model: "Animal study",
  review: "Review",
  database_record: "Database record",
};

/** HPO frequency terms used on has_phenotype edges */
export const HPO_FREQUENCY: Record<string, string> = {
  "HP:0040280": "Always present",
  "HP:0040281": "Very frequent (80–99%)",
  "HP:0040282": "Frequent (30–79%)",
  "HP:0040283": "Occasional (5–29%)",
  "HP:0040284": "Very rare (1–4%)",
  "HP:0040285": "Excluded (0%)",
};

export const THERAPY_STAGE_LABEL: Record<string, string> = {
  idea: "Idea",
  preclinical: "Preclinical (lab)",
  clinical: "In clinical trials",
  approved: "Approved",
};

export const THERAPY_MODALITY_LABEL: Record<string, string> = {
  gene_replacement: "Gene replacement",
  aso: "Antisense (ASO)",
  small_molecule: "Small-molecule drug",
  chaperone: "Chaperone",
  gene_editing: "Gene editing",
  repurposed_drug: "Repurposed drug",
  other: "Other",
};

/** Lower-cases the first letter only when it starts an ordinary word, so acronyms (SNARE, EEG) survive. */
export function lowerFirst(s: string): string {
  const first = s.split(/[\s/-]/)[0];
  if (/[\d+]/.test(first)) return s; // "Ca2+-triggered", "4-AP": keep symbols as written
  return /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s;
}

export function capFirst(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

export function joinList(items: string[], max = 3): string {
  if (items.length <= max) {
    if (items.length <= 1) return items.join("");
    return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
  }
  return `${items.slice(0, max).join(", ")} and ${items.length - max} more`;
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

export function isPlaceholderUrl(url?: string) {
  return !url || url === "#" || url.trim() === "";
}
