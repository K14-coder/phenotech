// Population layer (data/derived/population, synced to public/data/derived/population) and the web-side
// per-disease shards written by scripts/sync-data.mjs (public/data/derived/web/*). Everything is lazy and
// optional: web/available.json says which products exist, so pages never probe for missing files.
import { bucketOf } from "./global";

export interface PeopleRange {
  low: number | null;
  high: number | null;
  text?: string;
  n_entities?: number;
}

export interface PrevRecord {
  type?: string;
  qualification?: string;
  class?: string;
  area?: string;
  validation?: string;
  pmids?: string[];
  source?: string;
  mean_per_100k?: number;
  n_reported?: number;
}

export interface DeepPrevalence {
  label: string;
  mondo: string[];
  orpha_codes: string[];
  geographic_areas: string[];
  estimated_people: { worldwide?: PeopleRange; europe?: PeopleRange; us?: PeopleRange } | null;
  estimate_basis: string[];
  entities: { orpha: string; name: string; url: string; scope?: string; genes?: string[]; in_aggregate?: boolean; records: PrevRecord[] }[];
}

export interface PrevalenceFile {
  meta: { method?: string; source?: { name?: string; url?: string; licence?: string } };
  deep: Record<string, DeepPrevalence>;
}

export type ReadinessStatus = "yes" | "partial" | "no";

export interface ReadinessComponent {
  status: ReadinessStatus;
  edges: string[];
  note: string;
  highest_phase?: string | null;
  highest_phase_trial?: string | null;
}

export interface ReadinessEntry {
  label: string;
  family: string | null;
  tally: number;
  tally_of: number;
  yes: string[];
  components: Record<string, ReadinessComponent>;
  estimated_people_worldwide: string | null;
}

export interface ReadinessFile {
  meta: { rules?: Record<string, string>; tally?: string; source?: string };
  diseases: Record<string, ReadinessEntry>;
}

export interface Channel {
  id: string;
  type: string;
  name: string;
  url: string | null;
  how_to_reach?: string;
  layer?: string;
  diseases?: string[];
  evidence?: { edge?: string; scale?: string; url?: string }[];
  country?: string | null;
  scope?: string | null;
  reach_links?: { kind: string; url: string; link_text?: string }[];
  status?: string;
  phase?: string;
  study_type?: string;
  sponsor?: string;
}

export interface ChannelsFile {
  meta: { policy?: string };
  channels: Channel[];
  by_disease: Record<string, Record<string, string[]>>;
}

/** web/scale/<b>.json entry: patient organisations, studies, registries and prevalence at scale. */
export interface ScaleEntry {
  orgs: { n: string; u: string | null; c: string | null; src: string[]; q: string | null; p: string | null }[];
  studies: { id: string; t: string; st: string; ty: string; ph: string[]; en: number | null; sp: string | null; u: string; m?: string }[];
  regs: { n: string; u: string; k: string }[];
  /** open studies matched by the disease name, and those matched only through the gene */
  rec: number;
  recGene: number;
  n: number;
  active: number;
  prev?: { o: string; n: string; u: string; b: string | null; lo: number | null; hi: number | null; r: { t?: string; c?: string | null; a?: string | null; s?: string | null; n?: number | null }[] }[];
}

export interface Available {
  generated?: string;
  population: string[];
  scale: boolean;
  dismech: boolean;
  dismech_snippets: boolean;
  mechanism: boolean;
  groups?: boolean;
  sequences?: string[];
  variant_positions?: boolean;
  eval?: boolean;
  testing_options?: boolean;
  contacts?: boolean;
}

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
  return (await r.json()) as T;
}

const NONE: Available = { population: [], scale: false, dismech: false, dismech_snippets: false, mechanism: false };

export const AVAILABLE_KEY = "web:available";
export const loadAvailable = () => fetchJson<Available>("/data/derived/web/available.json").catch(() => NONE);

/** Loads a population file only when web/available.json lists it; otherwise resolves to null. */
export async function loadPopulationFile<T>(name: "prevalence.json" | "readiness.json" | "channels.json"): Promise<T | null> {
  const a = await loadAvailableOnce();
  if (!a.population.includes(name)) return null;
  return fetchJson<T>(`/data/derived/population/${name}`);
}

let availablePromise: Promise<Available> | null = null;
export function loadAvailableOnce() {
  availablePromise ??= loadAvailable();
  return availablePromise;
}

export const loadPrevalence = () => loadPopulationFile<PrevalenceFile>("prevalence.json");
export const loadReadiness = () => loadPopulationFile<ReadinessFile>("readiness.json");
export const loadChannels = () => loadPopulationFile<ChannelsFile>("channels.json");

export async function loadScale(id: string): Promise<ScaleEntry | null> {
  const a = await loadAvailableOnce();
  if (!a.scale) return null;
  const shard = await fetchJson<{ d: Record<string, ScaleEntry> }>(`/data/derived/web/scale/${bucketOf(id)}.json`);
  return shard.d[id] ?? null;
}

/** DisMech: one verbatim snippet per mechanism step, keyed by step index: [ref, snippet]. */
export async function loadDismechSnippets(mondo: string): Promise<Record<string, [string, string]> | null> {
  const a = await loadAvailableOnce();
  if (!a.dismech_snippets) return null;
  const shard = await fetchJson<{ d: Record<string, Record<string, [string, string]>> }>(`/data/derived/web/dismech_snippets/${bucketOf(mondo)}.json`);
  return shard.d[mondo] ?? null;
}

// ---------- wording helpers ----------

/** 8,100 -> "8,000"; 73,000 -> "73,000"; 340 -> "340"; 46 -> "50" (two significant figures, 1 for < 100). */
export function roundFriendly(n: number): string {
  if (n <= 0) return "0";
  const digits = n < 100 ? 1 : 2;
  const p = Math.pow(10, Math.max(0, Math.floor(Math.log10(n)) - digits + 1));
  return (Math.round(n / p) * p).toLocaleString("en-US");
}

/** "between about 8,000 and 73,000", "up to about 3,000", or null when there is no usable range. */
export function peopleRange(r: { low: number | null; high: number | null } | null | undefined): string | null {
  if (!r) return null;
  const { low, high } = r;
  if (high != null && (low == null || low <= 0)) return `up to about ${roundFriendly(high)}`;
  if (low != null && high == null) return `more than ${roundFriendly(low)}`;
  if (low != null && high != null) return low === high ? `about ${roundFriendly(low)}` : `between about ${roundFriendly(low)} and ${roundFriendly(high)}`;
  return null;
}

export const READINESS_LABEL: Record<string, string> = {
  registry_or_natural_history: "Registry or natural history study",
  outcome_measures_or_consortium: "Outcome measures or consortium",
  animal_or_cell_model: "Animal or cell models",
  interventional_trial: "Interventional trials",
  approved_therapy: "Approved therapy",
  patient_organisation: "Patient organisation",
  known_mechanism: "Known mechanism",
  research_groups_and_grants: "Research groups and funding",
};

export const CHANNEL_LABEL: Record<string, string> = {
  registry: "Registries",
  natural_history_study: "Natural history studies",
  data_platform: "Data platforms",
  biobank: "Biobanks",
  research_network: "Research networks",
  consortium: "Consortia",
  patient_org: "Patient organisations",
  recruiting_trial: "Trials recruiting now (sponsor level)",
};
