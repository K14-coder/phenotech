// Generates web/public/data/graph.json: a SMALL sample graph that follows docs/SCHEMA.md.
// Every evidence entry is an obvious placeholder (ref "SAMPLE", url "#", verified false).
// Gene names, HPO terms and mechanism names are real vocabulary; relationships and
// confidences are illustrative only. No PMIDs, NCT IDs or quotes are invented.
//
// Usage: node scripts/make-sample-graph.mjs
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "public", "data", "graph.json");
const TODAY = "2026-10-03";
const QUOTE = "SAMPLE placeholder. Real data shows the verbatim sentence from the source here.";

function ev(source, kind, extra = {}) {
  const extracted_by =
    kind === "computed" ? "computed" : kind === "database" ? "database" : "agent-curation";
  return {
    source,
    ref: "SAMPLE",
    url: "#",
    title: `Sample placeholder (${source}), not a real record`,
    kind,
    extracted_by,
    verified: false,
    retrieved: TODAY,
    ...(kind === "publication" || kind === "website" ? { quote: QUOTE } : {}),
    ...extra,
  };
}

function edge(source, type, target, o) {
  return {
    id: `${source}|${type}|${target}`,
    source,
    target,
    type,
    ...(o.label ? { label: o.label } : {}),
    explanation: o.explanation,
    evidence_level: o.level,
    status: o.status ?? "supported",
    confidence: o.confidence,
    evidence: o.evidence ?? [],
    ...(o.counter ? { counter_evidence: o.counter } : {}),
    ...(o.attrs ? { attrs: o.attrs } : {}),
  };
}

// ---------- nodes ----------
const nodes = [
  // genes
  {
    id: "gene:STXBP1", type: "gene", label: "STXBP1",
    synonyms: ["Munc18-1", "MUNC18-1", "UNC18A", "Syntaxin-binding protein 1"],
    xrefs: { HGNC: "HGNC:11444" },
    summary: "Gene that makes Munc18-1, a protein nerve cells need to release their chemical messages.",
    attrs: { protein: "Munc18-1", function: "Helps assemble the SNARE machinery that releases chemical messages at synapses." },
  },
  {
    id: "gene:SYT1", type: "gene", label: "SYT1",
    synonyms: ["Synaptotagmin-1"],
    summary: "Gene that makes synaptotagmin-1, the calcium sensor that tells a nerve cell exactly when to release a message.",
    attrs: { protein: "Synaptotagmin-1", function: "Calcium sensor that triggers fast message release." },
  },
  {
    id: "gene:SNAP25", type: "gene", label: "SNAP25",
    synonyms: ["SNAP-25", "Synaptosomal-associated protein 25"],
    summary: "Gene that makes SNAP-25, one of the core parts of the SNARE 'zipper' that fuses message packets with the cell wall.",
    attrs: { protein: "SNAP-25", function: "Core SNARE protein." },
  },
  {
    id: "gene:VAMP2", type: "gene", label: "VAMP2",
    synonyms: ["Synaptobrevin-2"],
    summary: "Gene that makes synaptobrevin-2, the SNARE protein that sits on the message packet itself.",
    attrs: { protein: "Synaptobrevin-2", function: "Core SNARE protein on synaptic vesicles." },
  },
  {
    id: "gene:STX1B", type: "gene", label: "STX1B",
    synonyms: ["Syntaxin-1B"],
    summary: "Gene that makes syntaxin-1B, a SNARE protein on the nerve cell's outer wall.",
    attrs: { protein: "Syntaxin-1B", function: "Core SNARE protein on the cell membrane." },
  },
  // diseases
  {
    id: "disease:STXBP1", type: "disease", label: "STXBP1-related disorders",
    synonyms: ["STXBP1 encephalopathy", "DEE4", "Developmental and epileptic encephalopathy 4"],
    xrefs: { OMIM: ["612164"] },
    summary: "A condition caused by changes in the STXBP1 gene. Children often have seizures that start early and delays in development.",
    attrs: { inheritance: "Autosomal dominant, usually a new (de novo) change", onset: "Infancy", approved_treatment: false },
  },
  {
    id: "disease:SYT1", type: "disease", label: "SYT1-related disorder",
    synonyms: ["Baker-Gordon syndrome", "SYT1-associated neurodevelopmental disorder"],
    summary: "A condition caused by changes in the SYT1 gene, mainly affecting development and movement.",
    attrs: { inheritance: "Autosomal dominant, usually de novo", approved_treatment: false },
  },
  {
    id: "disease:SNAP25", type: "disease", label: "SNAP25-related disorder",
    synonyms: ["SNAP25 encephalopathy"],
    summary: "A condition caused by changes in the SNAP25 gene, with seizures and developmental delay.",
    attrs: { inheritance: "Autosomal dominant, usually de novo", approved_treatment: false },
  },
  {
    id: "disease:VAMP2", type: "disease", label: "VAMP2-related disorder",
    synonyms: ["VAMP2 neurodevelopmental disorder"],
    summary: "A condition caused by changes in the VAMP2 gene, affecting development and muscle tone.",
    attrs: { inheritance: "Autosomal dominant, usually de novo", approved_treatment: false },
  },
  {
    id: "disease:STX1B", type: "disease", label: "STX1B-related epilepsy",
    synonyms: ["STX1B epilepsy"],
    summary: "A form of epilepsy linked to changes in the STX1B gene. Seizures can be triggered by fever.",
    attrs: { inheritance: "Autosomal dominant", approved_treatment: false },
  },
  // variant groups
  {
    id: "vg:STXBP1:truncating", type: "variant_group", label: "STXBP1 truncating changes",
    summary: "Gene changes that cut the Munc18-1 protein short.",
    attrs: { gene: "gene:STXBP1", consequence: "truncating" },
  },
  {
    id: "vg:STXBP1:missense", type: "variant_group", label: "STXBP1 missense changes",
    summary: "Gene changes that swap a single building block of the Munc18-1 protein.",
    attrs: { gene: "gene:STXBP1", consequence: "missense" },
  },
  // mechanisms
  {
    id: "mech:haploinsufficiency", type: "mechanism", label: "Haploinsufficiency",
    synonyms: ["Loss of function", "Too little protein"],
    summary: "One working copy of the gene is not enough, so the cell has too little of the protein.",
    attrs: { kind: "effect" },
  },
  {
    id: "mech:dominant-negative", type: "mechanism", label: "Dominant-negative effect",
    synonyms: ["Dominant negative"],
    summary: "The faulty protein gets in the way of the healthy protein made from the other copy.",
    attrs: { kind: "effect" },
  },
  {
    id: "mech:snare-complex-assembly", type: "mechanism", label: "SNARE complex assembly",
    synonyms: ["SNARE assembly", "SNAREopathy"],
    summary: "How a set of proteins zip together to pull message packets into the cell wall so the message can be released.",
    attrs: { kind: "process" },
  },
  {
    id: "mech:synaptic-vesicle-exocytosis", type: "mechanism", label: "Synaptic vesicle release",
    synonyms: ["Synaptic vesicle exocytosis", "Neurotransmitter release"],
    summary: "How a nerve cell releases its chemical messages to the next cell.",
    attrs: { kind: "process" },
  },
  // phenotypes (real HPO terms; information content values are illustrative)
  { id: "phenotype:HP:0001250", type: "phenotype", label: "Seizure", synonyms: ["Seizures", "Epileptic seizure"], summary: "A sudden burst of abnormal electrical activity in the brain.", attrs: { ic: 2.2 } },
  { id: "phenotype:HP:0001263", type: "phenotype", label: "Global developmental delay", synonyms: ["Developmental delay"], summary: "Reaching milestones like sitting, walking or talking later than expected.", attrs: { ic: 1.8 } },
  { id: "phenotype:HP:0001252", type: "phenotype", label: "Hypotonia", synonyms: ["Low muscle tone", "Floppiness"], summary: "Low muscle tone; the body can feel floppy.", attrs: { ic: 2.6 } },
  { id: "phenotype:HP:0001337", type: "phenotype", label: "Tremor", synonyms: ["Shaking"], summary: "Shaking movements that a person cannot control.", attrs: { ic: 4.1 } },
  { id: "phenotype:HP:0012469", type: "phenotype", label: "Infantile spasms", synonyms: ["West syndrome spasms"], summary: "A type of seizure in babies: brief, repeated jerks, often in clusters.", attrs: { ic: 5.4 } },
  // patient organizations (placeholders)
  {
    id: "org:sample-stxbp1-family-network", type: "patient_org", label: "STXBP1 family network (sample)",
    summary: "Placeholder patient organization used to demo the interface.",
    attrs: { url: "#", country: "International", scope: "Families affected by STXBP1-related disorders" },
  },
  {
    id: "org:sample-syt1-parents-group", type: "patient_org", label: "SYT1 parents group (sample)",
    summary: "Placeholder patient organization used to demo the interface.",
    attrs: { url: "#", country: "International", scope: "Families affected by SYT1-related disorder" },
  },
  // assets (placeholders)
  {
    id: "asset:sample-stxbp1-registry", type: "asset", label: "STXBP1 patient registry (sample)",
    summary: "Placeholder registry: families share health information so researchers can see patterns.",
    attrs: { kind: "registry", url: "#", access: "Apply to the maintaining organization", status: "Active (sample)" },
  },
  {
    id: "asset:sample-stxbp1-natural-history", type: "asset", label: "STXBP1 natural history study (sample)",
    summary: "Placeholder study that follows children over time to learn how the condition usually changes.",
    attrs: { kind: "natural_history_study", url: "#", status: "Enrolling (sample)" },
  },
  {
    id: "asset:sample-snap25-mouse-model", type: "asset", label: "SNAP25 mouse model (sample)",
    summary: "Placeholder animal model carrying a SNAP25 change.",
    attrs: { kind: "animal_model", url: "#", access: "On request (sample)" },
  },
  // study, therapy (placeholders)
  {
    id: "study:SAMPLE-0001", type: "study", label: "Protein-stabilizer trial in STXBP1 (sample)",
    summary: "Placeholder interventional study, used to demo how trials appear.",
    attrs: { status: "Recruiting (sample)", study_type: "interventional", phase: "Phase 2", sponsor: "Sample sponsor", url: "#", eligibility_note: "Placeholder: children with a confirmed STXBP1 change." },
  },
  {
    id: "therapy:sample-protein-stabilizer", type: "therapy", label: "Protein stabilizer (sample)",
    summary: "Placeholder therapy idea: a chaperone that helps a wobbly protein stay folded.",
    attrs: { modality: "chaperone", stage: "clinical" },
  },
  // hidden by default: researchers, grant, publication (placeholders)
  {
    id: "researcher:sample-researcher-a--sample-institute", type: "researcher", label: "Sample Researcher A",
    summary: "Placeholder researcher who works on both STXBP1 and SNAP25.",
    attrs: { affiliation: "Sample Institute" },
  },
  {
    id: "researcher:sample-researcher-b--sample-university", type: "researcher", label: "Sample Researcher B",
    summary: "Placeholder researcher who studies SYT1 and vesicle release.",
    attrs: { affiliation: "Sample University" },
  },
  {
    id: "grant:SAMPLE0001", type: "grant", label: "Sample grant on SNARE disorders",
    summary: "Placeholder research grant.",
    attrs: { title: "Sample grant on SNARE disorders (placeholder)", org: "Sample funder", fiscal_year: 2026, url: "#" },
  },
  {
    id: "pub:SAMPLE:1", type: "publication", label: "Sample publication (placeholder)",
    summary: "Placeholder publication node, shown only when publications are switched on.",
    attrs: { title: "Sample publication (placeholder)", year: 2026, url: "#" },
  },
];

// ---------- edges ----------
const db = (source, extra) => ev(source, "database", { study_type: "database_record", ...extra });
const pub = (study_type, extra) => ev("PubMed", "publication", { study_type, ...extra });
const atlas = () => ev("Atlas", "computed");
const site = () => ev("Website", "website");

const edges = [
  // gene -> disease
  edge("gene:STXBP1", "causes", "disease:STXBP1", { label: "causes", level: "curated", confidence: 0.95,
    explanation: "Changes in the STXBP1 gene cause STXBP1-related disorders.", evidence: [db("OMIM"), pub("case_series")] }),
  edge("gene:SYT1", "causes", "disease:SYT1", { label: "causes", level: "curated", confidence: 0.9,
    explanation: "Changes in the SYT1 gene cause SYT1-related disorder.", evidence: [db("OMIM"), pub("case_series")] }),
  edge("gene:SNAP25", "causes", "disease:SNAP25", { label: "causes", level: "curated", confidence: 0.85,
    explanation: "Changes in the SNAP25 gene cause SNAP25-related disorder.", evidence: [db("OMIM")] }),
  edge("gene:VAMP2", "causes", "disease:VAMP2", { label: "causes", level: "curated", confidence: 0.8,
    explanation: "Changes in the VAMP2 gene cause VAMP2-related disorder.", evidence: [db("OMIM")] }),
  edge("gene:STX1B", "causes", "disease:STX1B", { label: "causes", level: "curated", confidence: 0.85,
    explanation: "Changes in the STX1B gene are linked to this form of epilepsy.", evidence: [db("OMIM")] }),
  // variant groups
  edge("vg:STXBP1:truncating", "variant_in", "gene:STXBP1", { label: "change in", level: "curated", confidence: 0.85,
    explanation: "These are changes in the STXBP1 gene that cut the protein short.", evidence: [db("ClinVar")] }),
  edge("vg:STXBP1:missense", "variant_in", "gene:STXBP1", { label: "change in", level: "curated", confidence: 0.85,
    explanation: "These are changes in the STXBP1 gene that swap one protein building block.", evidence: [db("ClinVar")] }),
  edge("vg:STXBP1:truncating", "has_effect", "mech:haploinsufficiency", { label: "leads to", level: "experimental", confidence: 0.75,
    explanation: "When the protein is cut short, cells make about half the usual amount of working Munc18-1.",
    evidence: [pub("functional_study"), pub("functional_study")] }),
  edge("vg:STXBP1:missense", "has_effect", "mech:dominant-negative", { label: "may lead to", level: "experimental", status: "contested", confidence: 0.5,
    explanation: "Some lab studies suggest certain missense changes also disturb the healthy protein. Other studies found only reduced protein levels.",
    evidence: [pub("functional_study")], counter: [pub("functional_study", { supports: false })] }),
  // gene -> process
  edge("gene:STXBP1", "participates_in", "mech:snare-complex-assembly", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "Munc18-1, made by STXBP1, helps the SNARE proteins zip together.", evidence: [db("GO"), db("UniProt")] }),
  edge("gene:SNAP25", "participates_in", "mech:snare-complex-assembly", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "SNAP-25 is one of the core SNARE proteins.", evidence: [db("GO")] }),
  edge("gene:VAMP2", "participates_in", "mech:snare-complex-assembly", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "Synaptobrevin-2 is the SNARE protein on the message packet.", evidence: [db("GO")] }),
  edge("gene:STX1B", "participates_in", "mech:snare-complex-assembly", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "Syntaxin-1B is a SNARE protein on the cell wall.", evidence: [db("GO")] }),
  edge("gene:SYT1", "participates_in", "mech:synaptic-vesicle-exocytosis", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "Synaptotagmin-1 senses calcium and triggers message release.", evidence: [db("GO")] }),
  edge("gene:STXBP1", "participates_in", "mech:synaptic-vesicle-exocytosis", { label: "takes part in", level: "curated", confidence: 0.85,
    explanation: "Munc18-1 is needed for message packets to be released.", evidence: [db("GO")] }),
  // disease -> mechanism
  edge("disease:STXBP1", "driven_by", "mech:haploinsufficiency", { label: "driven by", level: "curated", confidence: 0.9,
    explanation: "Most children with STXBP1-related disorders have too little working Munc18-1 protein.",
    evidence: [db("ClinGen"), pub("cohort")] }),
  edge("disease:STXBP1", "driven_by", "mech:snare-complex-assembly", { label: "driven by", level: "experimental", confidence: 0.7,
    explanation: "With too little Munc18-1, the SNARE zipper assembles less well, so fewer messages are released.",
    evidence: [pub("functional_study"), pub("animal_model")] }),
  edge("disease:SNAP25", "driven_by", "mech:snare-complex-assembly", { label: "driven by", level: "experimental", confidence: 0.6,
    explanation: "SNAP25 changes disturb the SNARE zipper itself.", evidence: [pub("functional_study")] }),
  edge("disease:VAMP2", "driven_by", "mech:snare-complex-assembly", { label: "driven by", level: "experimental", confidence: 0.55,
    explanation: "VAMP2 changes disturb the SNARE protein on the message packet.", evidence: [pub("functional_study")] }),
  edge("disease:SYT1", "driven_by", "mech:synaptic-vesicle-exocytosis", { label: "driven by", level: "experimental", confidence: 0.65,
    explanation: "SYT1 changes alter how calcium triggers message release.", evidence: [pub("functional_study")] }),
  edge("disease:STX1B", "driven_by", "mech:snare-complex-assembly", { label: "probably driven by", level: "inferred", confidence: 0.4,
    explanation: "The atlas infers this because STX1B makes a SNARE protein. No study in the sample confirms it for this disease.",
    evidence: [atlas()] }),
  // disease -> phenotype
  edge("disease:STXBP1", "has_phenotype", "phenotype:HP:0001250", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "Seizures are common in STXBP1-related disorders.", evidence: [db("HPO")], attrs: { frequency: "HP:0040281" } }),
  edge("disease:STXBP1", "has_phenotype", "phenotype:HP:0001263", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "Developmental delay is common in STXBP1-related disorders.", evidence: [db("HPO")], attrs: { frequency: "HP:0040281" } }),
  edge("disease:STXBP1", "has_phenotype", "phenotype:HP:0001337", { label: "includes", level: "curated", confidence: 0.8,
    explanation: "Tremor is reported in some people with STXBP1-related disorders.", evidence: [db("HPO")], attrs: { frequency: "HP:0040282" } }),
  edge("disease:STXBP1", "has_phenotype", "phenotype:HP:0012469", { label: "includes", level: "observational", confidence: 0.65,
    explanation: "Some babies with STXBP1 changes have infantile spasms.", evidence: [pub("case_series")] }),
  edge("disease:SYT1", "has_phenotype", "phenotype:HP:0001263", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "Developmental delay is a main feature of SYT1-related disorder.", evidence: [db("HPO")] }),
  edge("disease:SYT1", "has_phenotype", "phenotype:HP:0001252", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "Low muscle tone is common in SYT1-related disorder.", evidence: [db("HPO")] }),
  edge("disease:SYT1", "has_phenotype", "phenotype:HP:0001337", { label: "includes", level: "observational", confidence: 0.6,
    explanation: "Tremor and other movement differences are reported in some people with SYT1 changes.", evidence: [pub("case_series")] }),
  edge("disease:SNAP25", "has_phenotype", "phenotype:HP:0001250", { label: "includes", level: "curated", confidence: 0.8,
    explanation: "Seizures are reported in SNAP25-related disorder.", evidence: [db("HPO")] }),
  edge("disease:SNAP25", "has_phenotype", "phenotype:HP:0001263", { label: "includes", level: "curated", confidence: 0.8,
    explanation: "Developmental delay is reported in SNAP25-related disorder.", evidence: [db("HPO")] }),
  edge("disease:VAMP2", "has_phenotype", "phenotype:HP:0001252", { label: "includes", level: "curated", confidence: 0.75,
    explanation: "Low muscle tone is reported in VAMP2-related disorder.", evidence: [db("HPO")] }),
  edge("disease:VAMP2", "has_phenotype", "phenotype:HP:0001263", { label: "includes", level: "curated", confidence: 0.75,
    explanation: "Developmental delay is reported in VAMP2-related disorder.", evidence: [db("HPO")] }),
  edge("disease:STX1B", "has_phenotype", "phenotype:HP:0001250", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "Seizures, often with fever, are the main feature.", evidence: [db("HPO")] }),
  // computed disease <-> disease
  edge("disease:STXBP1", "shares_mechanism", "disease:SNAP25", { label: "shares mechanism with", level: "inferred", confidence: 0.45,
    explanation: "Both conditions disturb the same SNARE zipper that nerve cells use to release messages.", evidence: [atlas()] }),
  edge("disease:STXBP1", "shares_mechanism", "disease:VAMP2", { label: "shares mechanism with", level: "inferred", confidence: 0.42,
    explanation: "Both conditions disturb SNARE assembly; VAMP2 makes the SNARE protein on the message packet.", evidence: [atlas()] }),
  edge("disease:STXBP1", "similar_phenotype", "disease:SYT1", { label: "similar symptoms to", level: "inferred", confidence: 0.38,
    explanation: "Both share developmental delay and tremor. Tremor is fairly distinctive, which makes the overlap more meaningful.", evidence: [atlas()] }),
  edge("disease:STXBP1", "similar_phenotype", "disease:STX1B", { label: "might resemble", level: "hypothesis", status: "unverified", confidence: 0.2,
    explanation: "Untested idea: both involve seizures and SNARE proteins, so they might respond to similar approaches. Seizures alone are a common symptom, so this is weak.",
    evidence: [] }),
  // community, assets, studies
  edge("org:sample-stxbp1-family-network", "serves", "disease:STXBP1", { label: "supports", level: "curated", confidence: 0.8,
    explanation: "This organization supports families affected by STXBP1-related disorders.", evidence: [site()] }),
  edge("org:sample-syt1-parents-group", "serves", "disease:SYT1", { label: "supports", level: "curated", confidence: 0.8,
    explanation: "This group supports families affected by SYT1-related disorder.", evidence: [site()] }),
  edge("org:sample-stxbp1-family-network", "maintains", "asset:sample-stxbp1-registry", { label: "runs", level: "curated", confidence: 0.8,
    explanation: "The family network runs this registry.", evidence: [site()] }),
  edge("asset:sample-stxbp1-registry", "covers", "disease:STXBP1", { label: "includes", level: "curated", confidence: 0.8,
    explanation: "The registry collects information from people with STXBP1-related disorders.", evidence: [site()] }),
  edge("asset:sample-stxbp1-natural-history", "covers", "disease:STXBP1", { label: "includes", level: "curated", confidence: 0.85,
    explanation: "This study follows people with STXBP1-related disorders over time.", evidence: [ev("ClinicalTrials.gov", "trial")] }),
  edge("asset:sample-snap25-mouse-model", "covers", "disease:SNAP25", { label: "models", level: "experimental", confidence: 0.6,
    explanation: "This mouse carries a SNAP25 change to model the condition.", evidence: [pub("animal_model")] }),
  edge("study:SAMPLE-0001", "studies", "disease:STXBP1", { label: "studies", level: "clinical", confidence: 0.85,
    explanation: "This trial enrolls people with STXBP1-related disorders.", evidence: [ev("ClinicalTrials.gov", "trial", { study_type: "clinical_trial" })] }),
  edge("study:SAMPLE-0001", "tests", "therapy:sample-protein-stabilizer", { label: "tests", level: "clinical", confidence: 0.85,
    explanation: "The trial tests the protein stabilizer.", evidence: [ev("ClinicalTrials.gov", "trial", { study_type: "clinical_trial" })] }),
  edge("therapy:sample-protein-stabilizer", "targets", "mech:haploinsufficiency", { label: "aims at", level: "experimental", confidence: 0.55,
    explanation: "The idea is to help the remaining protein stay stable, raising its amount.", evidence: [pub("functional_study")] }),
  // people and funding (hidden by default)
  edge("researcher:sample-researcher-a--sample-institute", "works_on", "gene:STXBP1", { label: "works on", level: "curated", confidence: 0.8,
    explanation: "This researcher has published on STXBP1.", evidence: [ev("NIH RePORTER", "grant")] }),
  edge("researcher:sample-researcher-a--sample-institute", "works_on", "gene:SNAP25", { label: "works on", level: "curated", confidence: 0.65,
    explanation: "This researcher has also published on SNAP25.", evidence: [pub("functional_study")] }),
  edge("researcher:sample-researcher-b--sample-university", "works_on", "disease:SYT1", { label: "works on", level: "curated", confidence: 0.65,
    explanation: "This researcher studies SYT1-related disorder.", evidence: [pub("cohort")] }),
  edge("researcher:sample-researcher-b--sample-university", "works_on", "mech:synaptic-vesicle-exocytosis", { label: "works on", level: "curated", confidence: 0.65,
    explanation: "This researcher studies how vesicles release messages.", evidence: [pub("functional_study")] }),
  edge("grant:SAMPLE0001", "funds", "researcher:sample-researcher-a--sample-institute", { label: "funds", level: "curated", confidence: 0.85,
    explanation: "This grant funds Researcher A's lab.", evidence: [ev("NIH RePORTER", "grant")] }),
  edge("researcher:sample-researcher-a--sample-institute", "authored", "pub:SAMPLE:1", { label: "wrote", level: "curated", confidence: 0.85,
    explanation: "Researcher A is an author of this publication.", evidence: [db("PubMed")] }),
];

const E = (s, t, d) => `${s}|${t}|${d}`;
const clusters = [
  {
    id: "cluster:snare-assembly", label: "SNARE assembly", basis: "mechanism",
    members: ["gene:STXBP1", "gene:SNAP25", "gene:VAMP2", "gene:STX1B", "disease:STXBP1", "disease:SNAP25", "disease:VAMP2", "disease:STX1B", "mech:snare-complex-assembly"],
    rationale: "These genes make parts of the SNARE 'zipper' or help it assemble. Different gene names, one shared job: releasing chemical messages between nerve cells.",
    edge_ids: [
      E("gene:STXBP1", "participates_in", "mech:snare-complex-assembly"), E("gene:SNAP25", "participates_in", "mech:snare-complex-assembly"),
      E("gene:VAMP2", "participates_in", "mech:snare-complex-assembly"), E("gene:STX1B", "participates_in", "mech:snare-complex-assembly"),
      E("disease:STXBP1", "shares_mechanism", "disease:SNAP25"), E("disease:STXBP1", "shares_mechanism", "disease:VAMP2"),
    ],
  },
  {
    id: "cluster:calcium-triggered-release", label: "Calcium-triggered release", basis: "pathway",
    members: ["gene:SYT1", "disease:SYT1", "mech:synaptic-vesicle-exocytosis"],
    rationale: "SYT1 acts one step later than the SNARE proteins: it senses calcium and decides when the message is released.",
    edge_ids: [E("gene:SYT1", "participates_in", "mech:synaptic-vesicle-exocytosis"), E("disease:SYT1", "driven_by", "mech:synaptic-vesicle-exocytosis")],
  },
  {
    id: "cluster:too-little-protein", label: "Too little working protein", basis: "mechanism",
    members: ["mech:haploinsufficiency", "mech:dominant-negative", "vg:STXBP1:truncating", "vg:STXBP1:missense", "therapy:sample-protein-stabilizer"],
    rationale: "Different gene changes that end in the same problem: not enough working protein. Therapies that raise protein levels could apply across them.",
    edge_ids: [E("vg:STXBP1:truncating", "has_effect", "mech:haploinsufficiency"), E("therapy:sample-protein-stabilizer", "targets", "mech:haploinsufficiency")],
  },
];

const searched = ["Sample placeholder: real data lists the directories and databases searched"];
const gaps = [
  {
    id: "gap:vamp2-community", about: "disease:VAMP2",
    question: "Is there a patient community for VAMP2-related disorder?",
    what_is_missing: ["A patient organization or family network", "A registry or natural history study"],
    searched,
    how_to_find_out: "Ask the clinic that made the diagnosis, and post in the closest related communities (STXBP1, SYT1) to find other VAMP2 families.",
  },
  {
    id: "gap:stx1b-mechanism", about: "disease:STX1B",
    question: "Is STX1B-related epilepsy caused by the same SNARE problem as STXBP1?",
    what_is_missing: ["Lab studies of how STX1B changes affect SNARE assembly", "A comparison of symptoms beyond seizures"],
    searched,
    how_to_find_out: "A lab that already measures SNARE assembly for STXBP1 could test a few STX1B changes with the same method.",
  },
  {
    id: "gap:stxbp1-missense-effect", about: "vg:STXBP1:missense",
    question: "Do some STXBP1 missense changes harm the healthy protein, or do they only lower the amount?",
    what_is_missing: ["Side-by-side tests of several missense changes in the same cell model"],
    searched,
    how_to_find_out: "Compare protein levels and function for a panel of missense changes in one shared cell model.",
  },
  {
    id: "gap:snap25-natural-history", about: "disease:SNAP25",
    question: "How does SNAP25-related disorder change over time?",
    what_is_missing: ["Natural history data", "Outcome measures tested in SNAP25 patients"],
    searched,
    how_to_find_out: "Ask whether the STXBP1 natural history study could open a SNAP25 arm using the same visit schedule.",
  },
];

const graph = {
  meta: {
    version: "0.1-sample",
    generated_at: TODAY,
    slice: "Synaptic vesicle release disorders (sample)",
    sample: true,
    sources: [{ name: "Sample placeholder data (no real sources)", version_or_date: TODAY, url: "#" }],
  },
  nodes,
  edges,
  clusters,
  gaps,
};

// sanity checks
const ids = new Set(nodes.map((n) => n.id));
for (const e of edges) {
  if (!ids.has(e.source) || !ids.has(e.target)) throw new Error(`dangling edge ${e.id}`);
  if (e.evidence_level !== "hypothesis" && e.evidence.length === 0) throw new Error(`no evidence ${e.id}`);
}
const edgeIds = new Set(edges.map((e) => e.id));
for (const c of clusters) {
  for (const m of c.members) if (!ids.has(m)) throw new Error(`bad member ${m}`);
  for (const id of c.edge_ids) if (!edgeIds.has(id)) throw new Error(`bad cluster edge ${id}`);
}
for (const g of gaps) if (!ids.has(g.about)) throw new Error(`bad gap ${g.id}`);

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(graph, null, 2) + "\n");
console.log(`wrote ${out}: ${nodes.length} nodes, ${edges.length} edges, ${clusters.length} clusters, ${gaps.length} gaps`);
