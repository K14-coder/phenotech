// Mirrors docs/SCHEMA.md (v0.1). Keep in sync with the contract.

export type NodeType =
  | "disease"
  | "gene"
  | "variant_group"
  | "mechanism"
  | "phenotype"
  | "patient_org"
  | "asset"
  | "study"
  | "publication"
  | "researcher"
  | "grant"
  | "therapy";

export const NODE_TYPES: NodeType[] = [
  "disease",
  "gene",
  "variant_group",
  "mechanism",
  "phenotype",
  "patient_org",
  "asset",
  "study",
  "therapy",
  "publication",
  "researcher",
  "grant",
];

// ---------- Evidence ----------

export type EvidenceSource =
  | "HGNC"
  | "MONDO"
  | "OMIM"
  | "Orphanet"
  | "HPO"
  | "ClinVar"
  | "ClinGen"
  | "GO"
  | "UniProt"
  | "PubMed"
  | "ClinicalTrials.gov"
  | "NIH RePORTER"
  | "OpenTargets"
  | "Monarch"
  | "Website"
  | "Atlas"
  | "Expert";

export type EvidenceKind =
  | "database"
  | "publication"
  | "trial"
  | "grant"
  | "website"
  | "computed"
  | "expert";

export type EvidenceStudyType =
  | "clinical_trial"
  | "case_report"
  | "case_series"
  | "cohort"
  | "functional_study"
  | "animal_model"
  | "review"
  | "database_record";

export type ExtractedBy =
  | "database"
  | "agent-curation"
  | `openai:${string}`
  | `human:${string}`
  | "computed";

export interface Evidence {
  source: EvidenceSource;
  /** "PMID:12345678", "NCT01234567", "OMIM:612164", "VCV000012345", or a URL */
  ref: string;
  url: string;
  title?: string;
  year?: number;
  /** VERBATIM text from the fetched source (required for PubMed and Website evidence) */
  quote?: string;
  kind: EvidenceKind;
  study_type?: EvidenceStudyType;
  /** default true; false means it contradicts the edge */
  supports?: boolean;
  extracted_by: ExtractedBy;
  /** true once the quote was string-matched against the stored source text, or a human checked it */
  verified?: boolean;
  /** YYYY-MM-DD */
  retrieved: string;
  /** an independent AI re-reading of this source ("openai:<model>" or "claude:<how>") */
  cross_checked?: { by: string; agrees: boolean; date: string };
  /** further independent readers of the same item (a second reader never overwrites the first stamp) */
  cross_checked_also?: { by: string; agrees: boolean; date: string }[];
  /** a contradiction found only by the OpenAI cross-check; not "contested" until a human confirms it */
  needs_review?: boolean;
}

// ---------- Node attrs ----------

export interface DiseaseSubtype {
  name: string;
  MONDO?: string;
  OMIM?: string;
  ORPHA?: string;
  inheritance?: string;
}

export interface DiseaseAttrs {
  subtypes?: DiseaseSubtype[];
  inheritance?: string;
  onset?: string;
  prevalence?: string;
  approved_treatment?: boolean;
}

export interface GeneAttrs {
  protein?: string;
  function?: string;
  protein_length_aa?: number;
  cds_length_bp?: number;
}

export interface VariantGroupAttrs {
  gene: string;
  consequence: "truncating" | "missense" | "splice" | "cnv" | "mixed";
  example_variants?: string[];
  clinvar_counts?: Record<string, number>;
}

export interface MechanismAttrs {
  kind: "effect" | "process";
  go_id?: string;
}

export interface PhenotypeAttrs {
  /** information content; higher = more specific / informative */
  ic: number;
  n_diseases?: number;
}

export interface PatientOrgAttrs {
  url: string;
  country?: string;
  scope?: string;
}

export type AssetKind =
  | "registry"
  | "natural_history_study"
  | "biobank"
  | "animal_model"
  | "cell_model"
  | "outcome_measure"
  | "assay"
  | "trial_design"
  | "research_network"
  | "funding_program"
  | "data_platform";

export interface AssetAttrs {
  kind: AssetKind;
  url?: string;
  access?: string;
  status?: string;
}

export interface StudyAttrs {
  status: string;
  study_type?: "interventional" | "observational";
  phase?: string;
  start?: string;
  sponsor?: string;
  enrollment?: number;
  interventions?: string[];
  conditions?: string[];
  eligibility_note?: string;
  url: string;
}

export interface PublicationAttrs {
  title: string;
  year: number;
  journal?: string;
  url: string;
  pub_type?: string;
}

/** Professional public info only. No personal contact details. */
export interface ResearcherAttrs {
  affiliation?: string;
  url?: string;
  orcid?: string;
}

export interface GrantAttrs {
  title: string;
  pis?: string[];
  org?: string;
  fiscal_year?: number;
  amount?: number;
  url: string;
}

export interface TherapyAttrs {
  modality:
    | "gene_replacement"
    | "aso"
    | "small_molecule"
    | "chaperone"
    | "gene_editing"
    | "repurposed_drug"
    | "other";
  stage: "idea" | "preclinical" | "clinical" | "approved";
}

// ---------- Nodes ----------

interface NodeCommon {
  id: string;
  label: string;
  /** for search and synonym resolution, e.g. "Munc18-1", "DEE4" */
  synonyms?: string[];
  xrefs?: Record<string, string | string[]>;
  /** 1–2 plain-language sentences */
  summary?: string;
  /** where this node comes from */
  sources?: Evidence[];
}

export type DiseaseNode = NodeCommon & { type: "disease"; attrs?: DiseaseAttrs };
export type GeneNode = NodeCommon & { type: "gene"; attrs?: GeneAttrs };
export type VariantGroupNode = NodeCommon & { type: "variant_group"; attrs?: VariantGroupAttrs };
export type MechanismNode = NodeCommon & { type: "mechanism"; attrs?: MechanismAttrs };
export type PhenotypeNode = NodeCommon & { type: "phenotype"; attrs?: PhenotypeAttrs };
export type PatientOrgNode = NodeCommon & { type: "patient_org"; attrs?: PatientOrgAttrs };
export type AssetNode = NodeCommon & { type: "asset"; attrs?: AssetAttrs };
export type StudyNode = NodeCommon & { type: "study"; attrs?: StudyAttrs };
export type PublicationNode = NodeCommon & { type: "publication"; attrs?: PublicationAttrs };
export type ResearcherNode = NodeCommon & { type: "researcher"; attrs?: ResearcherAttrs };
export type GrantNode = NodeCommon & { type: "grant"; attrs?: GrantAttrs };
export type TherapyNode = NodeCommon & { type: "therapy"; attrs?: TherapyAttrs };

export type AtlasNode =
  | DiseaseNode
  | GeneNode
  | VariantGroupNode
  | MechanismNode
  | PhenotypeNode
  | PatientOrgNode
  | AssetNode
  | StudyNode
  | PublicationNode
  | ResearcherNode
  | GrantNode
  | TherapyNode;

// ---------- Edges ----------

export type RelationType =
  | "causes"
  | "variant_in"
  | "has_effect"
  | "participates_in"
  | "driven_by"
  | "has_phenotype"
  | "shares_mechanism"
  | "similar_phenotype"
  | "serves"
  | "maintains"
  | "covers"
  | "studies"
  | "tests"
  | "targets"
  | "developed_for"
  | "works_on"
  | "authored"
  | "funds"
  | "about"
  | "candidate_for"
  // computed disease-disease links on six mechanistic axes (pipeline/derive/mechsim.py)
  | "shares_gene"
  | "shares_pathway"
  | "shares_tissue"
  | "similar_mutation_spectrum"
  | "similar_protein_fate"
  | "similar_protein_structure"
  | "shares_pharmacology"
  | "mechanistically_similar";

/** The computed mechanistic-similarity link types (hidden on the map unless switched on). */
export const MECHSIM_RELATIONS: readonly RelationType[] = [
  "shares_gene",
  "shares_pathway",
  "shares_tissue",
  "similar_mutation_spectrum",
  "similar_protein_fate",
  "similar_protein_structure",
  "shares_pharmacology",
  "mechanistically_similar",
];

export type EvidenceLevel =
  | "clinical"
  | "curated"
  | "experimental"
  | "observational"
  | "inferred"
  | "hypothesis";

export type EdgeStatus = "supported" | "contested" | "unverified";

export interface AtlasEdge {
  /** deterministic: `${source}|${type}|${target}` */
  id: string;
  source: string;
  target: string;
  type: RelationType;
  /** short verb phrase for hover */
  label?: string;
  /** 1–2 sentences a family can follow; restates the evidence only */
  explanation: string;
  evidence_level: EvidenceLevel;
  status: EdgeStatus;
  /** 0–1, see rubric */
  confidence: number;
  /** >= 1 unless evidence_level is "hypothesis" */
  evidence: Evidence[];
  /** contradicting or limiting findings: show them, never hide them */
  counter_evidence?: Evidence[];
  attrs?: Record<string, unknown>;
  /** human review record (data/curated/overrides.json) */
  review?: EdgeReview;
}

export interface EdgeReview {
  by: string;
  date: string;
  /** "ai-review:<model>" for the independent AI review (not a human expert); anything else is a human reviewer */
  verdict: "confirmed" | "corrected" | "rejected" | "needs-human";
  note?: string;
}

/** Review records written by the independent AI review pass, kept apart from human expert review. */
export const isAiReview = (r?: { by?: string } | null) => !!r?.by?.startsWith("ai-review:");

// ---------- Top level ----------

export interface Cluster {
  id: string;
  label: string;
  basis: "mechanism" | "phenotype" | "pathway";
  members: string[];
  rationale: string;
  edge_ids: string[];
}

export interface Gap {
  id: string;
  about: string;
  question: string;
  what_is_missing: string[];
  searched: string[];
  how_to_find_out: string;
}

export interface GraphMeta {
  version: string;
  generated_at: string;
  slice: string;
  sample?: boolean;
  sources: { name: string; version_or_date: string; url: string }[];
}

export interface AtlasGraph {
  meta: GraphMeta;
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  clusters: Cluster[];
  gaps: Gap[];
}
