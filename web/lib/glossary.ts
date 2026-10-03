// One-line, plain-language explanations for terms a parent may not know.
// Keys are lower-case; lookups normalise case, hyphens and plurals.

export const GLOSSARY: Record<string, string> = {
  haploinsufficiency:
    "One working copy of the gene isn't enough: the body makes about half the usual protein, and that's too little.",
  "loss of function": "The gene change stops the protein from doing its job.",
  "gain of function": "The gene change makes the protein overactive or gives it a new, harmful job.",
  "dominant-negative effect": "The faulty protein gets in the way of the healthy protein made from the other copy.",
  "dominant negative": "The faulty protein gets in the way of the healthy protein made from the other copy.",
  destabilization: "The protein is made but falls apart too quickly.",
  "snare complex assembly":
    "SNARE proteins zip together like a zipper to pull a tiny message packet into the cell wall, so a nerve cell can release its message.",
  snare: "A set of proteins that zip together so nerve cells can release chemical messages.",
  "synaptic vesicle release": "How a nerve cell releases its chemical messages to the next cell.",
  "synaptic vesicle exocytosis": "How a nerve cell releases its chemical messages to the next cell.",
  "synaptic vesicle": "A tiny bubble inside a nerve cell that carries chemical messages.",
  mechanism: "What actually goes wrong in the body, or the biological process involved.",
  phenotype: "A feature or symptom you can observe, like seizures or low muscle tone.",
  symptom: "A feature you can observe, like seizures or low muscle tone.",
  "natural history study":
    "A study that follows people with a condition over time to learn how it usually changes. Trials need it as a baseline.",
  registry: "A shared, organised collection of health information from people with a condition.",
  "de novo": "A new gene change in the child, not inherited from either parent.",
  "autosomal dominant": "One changed copy of the gene is enough to cause the condition.",
  "autosomal recessive": "Both copies of the gene must be changed to cause the condition.",
  missense: "A gene change that swaps one building block of the protein for another.",
  truncating: "A gene change that cuts the protein short.",
  splice: "A gene change that disrupts how the gene's instructions are cut and joined.",
  "information content": "How specific a symptom is. Rare, distinctive symptoms tell you more than common ones.",
  encephalopathy: "A general term for a brain that isn't working as it should.",
  "developmental and epileptic encephalopathy":
    "A group of conditions where seizures and developmental problems happen together.",
  hypotonia: "Low muscle tone; the body can feel floppy.",
  ataxia: "Problems with balance and coordination.",
  chaperone: "A medicine designed to help a wobbly protein fold properly and stay stable.",
  aso: "Antisense oligonucleotide: a short genetic molecule that can change how much protein a gene makes.",
  "animal model": "An animal, often a mouse, carrying the same gene change so researchers can study it.",
  "cell model": "Cells grown in the lab that carry the gene change, used to test ideas quickly.",
  "outcome measure": "An agreed way to measure whether a treatment helps.",
  inferred: "The atlas computed this connection from shared features. No paper states it directly.",
  hypothesis: "An idea worth testing. It is not established.",
  confidence: "How strongly the sources support this connection, from 0 (none) to 1 (very strong).",
  "contested": "Sources disagree about this connection. Both sides are shown.",
  centrality:
    "How much something links the rest of the atlas together: how often it sits on the shortest route between two other things, ranked from 0 to 100.",
  "cross-cluster bridge":
    "A link that crosses a cluster boundary: a disease outside the family, or a medicine from another cluster. Unexpected collaborations often start here.",
};

function normalise(term: string): string {
  return term.toLowerCase().replace(/[‐-–]/g, "-").replace(/\s+/g, " ").trim();
}

export function explain(term: string | undefined | null): string | undefined {
  if (!term) return undefined;
  const t = normalise(term);
  if (GLOSSARY[t]) return GLOSSARY[t];
  const noHyphen = t.replace(/-/g, " ");
  if (GLOSSARY[noHyphen]) return GLOSSARY[noHyphen];
  if (t.endsWith("s") && GLOSSARY[t.slice(0, -1)]) return GLOSSARY[t.slice(0, -1)];
  return undefined;
}
