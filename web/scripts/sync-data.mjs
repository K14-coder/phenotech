// Copies the merged graph produced by the pipeline into the web app.
//   ../data/graph.json  ->  public/data/graph.json   (only if the source exists)
//   ../data/ai/*.json   ->  public/data/ai/           (optional precomputed AI outputs)
// If ../data/graph.json is missing, the committed sample graph stays in place.
// Runs automatically before `npm run dev` and `npm run build`.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const dataRoot = join(webRoot, "..", "data");
const src = join(dataRoot, "graph.json");
const dest = join(webRoot, "public", "data", "graph.json");

if (existsSync(src)) {
  try {
    const g = JSON.parse(readFileSync(src, "utf8"));
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
    console.log(
      `[sync-data] copied ../data/graph.json (${g.nodes?.length ?? "?"} nodes, ${g.edges?.length ?? "?"} edges${g.meta?.sample ? ", sample" : ""})`,
    );
  } catch (err) {
    console.warn(`[sync-data] ../data/graph.json is not valid JSON, keeping the existing file: ${err.message}`);
  }
} else {
  console.log("[sync-data] ../data/graph.json not found, using public/data/graph.json as is");
}

// derived data products (lazy-loaded by the pages that need them)
//   ../data/derived/*.json            -> public/data/derived/
//   ../data/curated/{modality,impact,testing_options}.json -> public/data/curated/
const copyJson = (from, toDir, names) => {
  if (!existsSync(from)) return 0;
  mkdirSync(toDir, { recursive: true });
  let n = 0;
  for (const f of names ?? readdirSync(from).filter((x) => x.endsWith(".json"))) {
    const src = join(from, f);
    if (!existsSync(src)) continue;
    try {
      JSON.parse(readFileSync(src, "utf8"));
    } catch (err) {
      console.warn(`[sync-data] skipping ${f}: not valid JSON (${err.message})`);
      continue;
    }
    copyFileSync(src, join(toDir, f));
    n++;
  }
  return n;
};
const nDerived = copyJson(join(dataRoot, "derived"), join(webRoot, "public", "data", "derived"));
const nCurated = copyJson(join(dataRoot, "curated"), join(webRoot, "public", "data", "curated"), ["modality.json", "impact.json", "testing_options.json"]);
if (nDerived || nCurated) console.log(`[sync-data] copied ${nDerived} derived and ${nCurated} curated file(s)`);

// global disease index (every rare disease, basic data; see data/derived/global/README.md), folder
// structure kept: index.json, meta.json, neighbours/<0-63>.json and any later shard folders
//   ../data/derived/global/**/*.json -> public/data/derived/global/**
// dismech_evidence/ (87 MB of full DisMech evidence) stays out of the deploy; the few snippets the pages
// show are distilled into public/data/derived/web/dismech_snippets/ below
const GLOBAL_EXCLUDE = new Set(["dismech_evidence"]);
// every file (FASTA/VCF examples are not JSON); JSON is still validated
const copyTreeAll = (from, to) => {
  if (!existsSync(from)) return 0;
  mkdirSync(to, { recursive: true });
  let n = 0;
  for (const ent of readdirSync(from, { withFileTypes: true })) {
    const s = join(from, ent.name);
    const d = join(to, ent.name);
    if (ent.isDirectory()) n += copyTreeAll(s, d);
    else if (!ent.name.startsWith(".")) {
      if (ent.name.endsWith(".json")) {
        try {
          JSON.parse(readFileSync(s, "utf8"));
        } catch {
          console.warn(`[sync-data] skipping ${ent.name}: not valid JSON`);
          continue;
        }
      }
      copyFileSync(s, d);
      n++;
    }
  }
  return n;
};
const copyTree = (from, to) => {
  const out = { files: 0, bytes: 0, skipped: 0 };
  if (!existsSync(from)) return out;
  mkdirSync(to, { recursive: true });
  for (const ent of readdirSync(from, { withFileTypes: true })) {
    const s = join(from, ent.name);
    const d = join(to, ent.name);
    if (ent.isDirectory()) {
      if (GLOBAL_EXCLUDE.has(ent.name)) continue;
      const sub = copyTree(s, d);
      out.files += sub.files;
      out.bytes += sub.bytes;
      out.skipped += sub.skipped;
    } else if (ent.name.endsWith(".json")) {
      const text = readFileSync(s, "utf8");
      try {
        JSON.parse(text);
      } catch (err) {
        console.warn(`[sync-data] skipping global/${ent.name}: not valid JSON (${err.message})`);
        out.skipped++;
        continue;
      }
      copyFileSync(s, d);
      out.files++;
      out.bytes += Buffer.byteLength(text);
    }
  }
  return out;
};
{
  const g = copyTree(join(dataRoot, "derived", "global"), join(webRoot, "public", "data", "derived", "global"));
  if (g.files) console.log(`[sync-data] copied ${g.files} global index file(s), ${(g.bytes / 1e6).toFixed(1)} MB${g.skipped ? `, ${g.skipped} skipped` : ""}`);
}

// ---------- web-side per-disease shards (djb2(id) % 64, same as the global index) ----------
// public/data/derived/web/scale/<b>.json: patient organisations, trials and registries at scale
// (data/derived/scale) keyed by global row id AND by atlas disease id, so a page loads one small shard.
// public/data/derived/web/dismech_snippets/<b>.json: one verbatim evidence snippet per DisMech step.
const djb2 = (str) => {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = (Math.imul(h, 33) + str.charCodeAt(i)) >>> 0;
  return h;
};
const readJson = (p) => {
  try {
    return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : null;
  } catch (err) {
    console.warn(`[sync-data] ${p}: ${err.message}`);
    return null;
  }
};
const writeShards = (dir, entries) => {
  mkdirSync(dir, { recursive: true });
  const buckets = Array.from({ length: 64 }, () => ({}));
  for (const [id, v] of entries) buckets[djb2(id) % 64][id] = v;
  buckets.forEach((d, b) => writeFileSync(join(dir, `${b}.json`), JSON.stringify({ bucket: b, d })));
};
{
  const gdir = join(dataRoot, "derived", "global");
  const idxRows = [];
  for (const name of ["index.json", "index_extra.json"]) {
    const j = readJson(join(gdir, name));
    if (!j) continue;
    const F = Object.fromEntries(j.f.map((k, i) => [k, i]));
    for (const r of j.rows) idxRows.push({ id: r[F.id], omim: String(r[F.omim] || ""), orpha: String(r[F.orpha] || ""), atlas: r[F.atlas] || null });
  }
  // OMIM:/ORPHA:/MONDO: key -> row id, and row id -> atlas id
  const toRow = new Map();
  const atlasOf = new Map();
  for (const r of idxRows) {
    toRow.set(r.id, r.id);
    for (const o of r.omim.split(",").filter(Boolean)) toRow.set(`OMIM:${o}`, r.id);
    for (const o of r.orpha.split(",").filter(Boolean)) toRow.set(`ORPHA:${o}`, r.id);
    if (r.atlas) atlasOf.set(r.id, r.atlas);
  }
  const graph = readJson(join(webRoot, "public", "data", "graph.json"));
  for (const n of graph?.nodes ?? []) {
    if (n.type !== "disease") continue;
    for (const [db, v] of Object.entries(n.xrefs ?? {}))
      for (const x of Array.isArray(v) ? v : [v]) {
        const key = String(x).includes(":") ? String(x) : `${db}:${x}`;
        const row = toRow.get(key);
        if (row && !atlasOf.has(row)) atlasOf.set(row, n.id);
      }
  }
  const sdir = join(dataRoot, "derived", "scale");
  const orgs = readJson(join(sdir, "orgs.json"));
  const trials = readJson(join(sdir, "trials.json"));
  const assets = readJson(join(sdir, "assets.json"));
  if (orgs || trials || assets) {
    const acc = new Map();
    const get = (id) => {
      let e = acc.get(id);
      if (!e) acc.set(id, (e = { orgs: new Map(), studies: new Map(), regs: new Map(), rec: 0, recGene: 0, n: 0, active: 0 }));
      return e;
    };
    const targets = (key, mondo) => {
      const row = toRow.get(key) ?? (mondo ? toRow.get(mondo) : undefined);
      if (!row) return [];
      return atlasOf.has(row) ? [row, atlasOf.get(row)] : [row];
    };
    const trim = (t, n = 220) => (t && t.length > n ? `${t.slice(0, n - 1)}…` : t);
    for (const o of orgs?.orgs ?? []) {
      const rec = o.directory_records?.find((r) => r.quote) ?? null;
      const card = { n: o.name, u: o.website ?? o.url ?? null, c: o.country ?? null, src: o.sources ?? [], q: trim(rec?.quote ?? null), p: rec?.profile ?? rec?.url ?? o.directory_profile ?? null };
      for (const d of o.diseases ?? []) for (const t of targets(d.id, d.mondo)) get(t).orgs.set(o.id, card);
    }
    const OPEN = ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"];
    for (const [key, d] of Object.entries(trials?.diseases ?? {})) {
      for (const t of targets(key, d.mondo)) {
        const e = get(t);
        const open = (b) => OPEN.reduce((n, k) => n + (b?.by_status?.[k] ?? 0), 0);
        e.rec = Math.max(e.rec, open(d.by_name));
        e.recGene = Math.max(e.recGene, open(d.by_gene));
        e.n = Math.max(e.n, d.by_name?.n ?? 0);
        e.active = Math.max(e.active, d.by_name?.active ?? 0);
        for (const top of d.top ?? []) {
          const st = trials.studies?.[top.nct];
          if (!st || e.studies.has(top.nct)) continue;
          e.studies.set(top.nct, { id: top.nct, t: st.title, st: st.status, ty: st.type, ph: st.phases ?? [], en: st.enrollment ?? null, sp: st.sponsor ?? null, u: st.url, m: top.rule });
        }
      }
    }
    for (const a of assets?.assets ?? [])
      for (const d of a.diseases ?? [])
        for (const k of d.ids ?? []) for (const t of targets(k)) get(t).regs.set(a.id, { n: a.name, u: a.url, k: a.kind });
    // prevalence (data/derived/population/prevalence_orpha.json) for every row with ORPHA codes
    const prevO = readJson(join(dataRoot, "derived", "population", "prevalence_orpha.json"));
    if (prevO?.orpha) {
      for (const r of idxRows) {
        const list = [];
        for (const o of r.orpha.split(",").filter(Boolean)) {
          const p = prevO.orpha[o];
          if (!p || (!p.records?.length && !p.estimate)) continue;
          const ww = p.estimate?.worldwide;
          list.push({
            o,
            n: p.name,
            u: p.url,
            b: p.estimate?.basis ?? null,
            lo: ww?.low ?? null,
            hi: ww?.high ?? null,
            r: (p.records ?? []).slice(0, 4).map((x) => ({ t: x.type, c: x.class ?? null, a: x.area ?? null, s: x.source ?? null, n: x.n_reported ?? null })),
          });
        }
        if (list.length) get(r.id).prev = list;
      }
    }
    writeShards(
      join(webRoot, "public", "data", "derived", "web", "scale"),
      [...acc].map(([id, e]) => [id, { orgs: [...e.orgs.values()], studies: [...e.studies.values()].slice(0, 12), regs: [...e.regs.values()], rec: e.rec, recGene: e.recGene, n: e.n, active: e.active, ...(e.prev ? { prev: e.prev } : {}) }]),
    );
    console.log(`[sync-data] wrote web/scale shards for ${acc.size} diseases`);
  }
  // DisMech: first supporting snippet per step, from the full evidence that is not deployed
  const evDir = join(gdir, "dismech_evidence");
  if (existsSync(evDir)) {
    const out = [];
    for (const fname of readdirSync(evDir).filter((x) => x.endsWith(".json"))) {
      const j = readJson(join(evDir, fname));
      for (const [mondo, list] of Object.entries(j?.d ?? {})) {
        const steps = {};
        for (const [k, v] of Object.entries(list?.[0]?.x ?? {})) {
          if (!k.startsWith("steps/")) continue;
          const ev = (v.evidence ?? []).find((e) => e.supports === "SUPPORT" && e.snippet) ?? null;
          if (ev) steps[k.slice(6)] = [ev.ref, ev.snippet.length > 280 ? `${ev.snippet.slice(0, 279)}…` : ev.snippet];
        }
        if (Object.keys(steps).length) out.push([mondo, steps]);
      }
    }
    writeShards(join(webRoot, "public", "data", "derived", "web", "dismech_snippets"), out);
    console.log(`[sync-data] wrote DisMech snippet shards for ${out.length} disorders`);
  }
}

// population layer (prevalence, readiness, channels; produced by another agent) and a list of the
// optional products that exist, so pages never probe for missing files (each probe logs a 404)
{
  // reference CDS per deep gene and synthetic example FASTA/VCF files for /sequence
  const sq = copyTreeAll(join(dataRoot, "derived", "sequences"), join(webRoot, "public", "data", "derived", "sequences"));
  if (sq) console.log(`[sync-data] copied ${sq} sequence file(s)`);
  const exDir = join(webRoot, "public", "data", "derived", "sequences", "examples");
  mkdirSync(join(webRoot, "public", "data", "derived", "web"), { recursive: true });
  writeFileSync(
    join(webRoot, "public", "data", "derived", "web", "sequence_examples.json"),
    JSON.stringify({ files: existsSync(exDir) ? readdirSync(exDir).filter((f) => /\.(fasta|fa|vcf|vcf\.gz)$/i.test(f)).sort() : [] }, null, 2) + "\n",
  );
  const p = copyTree(join(dataRoot, "derived", "population"), join(webRoot, "public", "data", "derived", "population"));
  // prevalence_orpha.json (5.7 MB) is distilled into web/scale shards above; pages never load it
  try {
    rmSync(join(webRoot, "public", "data", "derived", "population", "prevalence_orpha.json"));
  } catch {
    // not there
  }
  if (p.files) console.log(`[sync-data] copied ${p.files} population file(s)`);
  // contacts: organisations' published general emails / phones and ClinicalTrials.gov central contacts
  // (data/derived/contacts/{orgs,trials}.json); a stale copy is removed when the source is gone
  {
    const cdst = join(webRoot, "public", "data", "derived", "contacts");
    // slimmed for the browser: no names (CT.gov central contacts keep only phone / email), no snippets
    const csrc = join(dataRoot, "derived", "contacts");
    const orgsC = readJson(join(csrc, "orgs.json"));
    const trialsC = readJson(join(csrc, "trials.json"));
    if (orgsC || trialsC) {
      mkdirSync(cdst, { recursive: true });
      const EM = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      const orgs = {};
      for (const [id, o] of Object.entries(orgsC?.orgs ?? {})) {
        const e = (o.emails ?? []).filter((x) => EM.test(x)).slice(0, 2);
        const p = (o.phones ?? []).filter((x) => x?.number).slice(0, 2).map((x) => ({ d: x.number, t: x.e164 ?? null }));
        if (!e.length && !p.length) continue;
        const ev = [...(o.email_evidence ?? []), ...(o.phone_evidence ?? [])][0];
        orgs[id] = { n: o.name, w: o.website ?? null, e, p, u: ev?.source_url ?? o.contact_page_url ?? o.source_url ?? null, r: ev?.retrieved ?? o.retrieved ?? null };
      }
      const trials = {};
      for (const [nct, t] of Object.entries(trialsC?.trials ?? {})) {
        if (!["RECRUITING", "NOT_YET_RECRUITING"].includes(t.status)) continue;
        const c = (t.central_contacts ?? []).find((x) => x.email || x.phone);
        if (!c) continue;
        trials[nct] = { e: c.email && EM.test(c.email) ? c.email : null, p: c.phone ? { d: c.phone + (c.phoneExt ? ` ext. ${c.phoneExt}` : ""), t: c.e164 ?? null } : null, r: t.retrieved ?? null };
      }
      // organisations whose own website was checked (with or without a contact), so the UI can say "we looked"
      // scope of the extraction (data/raw/contacts/orgs_extracted.json: every org whose site was read, 473), else the derived orgs
      const scopeC = readJson(join(dataRoot, "raw", "contacts", "orgs_extracted.json"));
      const checked = Object.entries(scopeC?.orgs ?? orgsC?.orgs ?? {})
        .filter(([, o]) => o.url ?? o.website)
        .map(([id, o]) => [id, o.url ?? o.website]);
      // named contact persons that an organisation publishes on its own site (data/derived/contacts/people.json)
      const peopleC = readJson(join(csrc, "people.json"));
      const people = {};
      const plist = Array.isArray(peopleC?.people)
        ? peopleC.people
        : Object.entries(peopleC?.people ?? peopleC?.orgs ?? {}).flatMap(([oid, v]) => (Array.isArray(v) ? v : (v?.people ?? [])).map((x) => ({ org_id: oid, ...x })));
      for (const x of plist) {
        const oid = x.org_id ?? x.org ?? x.organisation_id;
        // never individual researchers (also guarded by role words), only an organisation's own named contacts
        if (!oid || !x.name || x.kind === "researcher" || x.is_researcher || /\b(professor|principal investigator|investigator|researcher|scientist|postdoc|ph\.?d\.? (student|candidate)|lab (head|lead))\b/i.test(x.role ?? "")) continue;
        const e = (x.emails ?? (x.email ? [x.email] : [])).filter((m) => EM.test(m)).slice(0, 1);
        const ph = (x.phones ?? (x.phone ? [x.phone] : [])).map((q) => (typeof q === "string" ? { d: q, t: null } : { d: q.number ?? q.display ?? "", t: q.e164 ?? null })).filter((q) => q.d).slice(0, 1);
        (people[oid] ??= []).push({ n: x.name, r: x.role ?? null, e, p: ph, u: x.page_url ?? x.source_url ?? null, r2: x.retrieved ?? null });
      }
      writeFileSync(join(cdst, "orgs.json"), JSON.stringify({ built: orgsC?.meta?.built ?? null, orgs, checked, people }));
      writeFileSync(join(cdst, "trials.json"), JSON.stringify({ built: trialsC?.meta?.built ?? null, trials }));
      console.log(`[sync-data] contacts: ${Object.keys(orgs).length} organisations (${checked.length} websites checked, ${Object.values(people).flat().length} named contacts), ${Object.keys(trials).length} recruiting studies (names dropped)`);
    } else if (existsSync(cdst)) rmSync(cdst, { recursive: true, force: true });
  }
  // full ClinVar P/LP shards (data/derived/ingest/clinvar/<djb2(gene)%64>.json), loaded one shard at a time by
  // /sequence and /variant, plus a position -> gene interval index built from their exact keys, so a VCF line
  // finds its gene shard by position alone
  {
    const idir = join(dataRoot, "derived", "ingest");
    const cvDst = join(webRoot, "public", "data", "derived", "ingest", "clinvar");
    const nCv = copyTreeAll(join(idir, "clinvar"), cvDst);
    if (nCv) {
      const spans = { GRCh38: new Map(), GRCh37: new Map() };
      for (const f of readdirSync(cvDst).filter((x) => x.endsWith(".json"))) {
        const shard = readJson(join(cvDst, f));
        const F = Object.fromEntries((shard?.f ?? []).map((k, i) => [k, i]));
        for (const [gene, g] of Object.entries(shard?.g ?? {})) {
          for (const v of g.v ?? []) {
            for (const asm of ["GRCh38", "GRCh37"]) {
              const key = v[F[asm.toLowerCase()]];
              if (!key) continue;
              const [chrom, posS] = key.split(":");
              const pos = Number(posS);
              if (!Number.isFinite(pos)) continue;
              const k = `${chrom}|${gene}`;
              const cur = spans[asm].get(k);
              if (!cur) spans[asm].set(k, [pos, pos]);
              else {
                if (pos < cur[0]) cur[0] = pos;
                if (pos > cur[1]) cur[1] = pos;
              }
            }
          }
        }
      }
      const out = { note: "chrom -> [start, end, gene] sorted by start: span of each gene's ClinVar P/LP keys (+-200 bp)", GRCh38: {}, GRCh37: {} };
      for (const asm of ["GRCh38", "GRCh37"]) {
        for (const [k, [a, b]] of spans[asm]) {
          const [chrom, gene] = k.split("|");
          (out[asm][chrom] ??= []).push([Math.max(1, a - 200), b + 200, gene]);
        }
        for (const c of Object.keys(out[asm])) out[asm][c].sort((x, y) => x[0] - y[0]);
      }
      mkdirSync(join(webRoot, "public", "data", "derived", "web"), { recursive: true });
      writeFileSync(join(webRoot, "public", "data", "derived", "web", "clinvar_genes.json"), JSON.stringify(out));
      console.log(`[sync-data] copied ${nCv} ClinVar shard(s) and wrote web/clinvar_genes.json (${spans.GRCh38.size} gene spans on GRCh38)`);
    }
    // explanatory gene factors (gnomAD constraint, ClinVar spectrum, AlphaMissense), sharded by djb2(gene)%64
    const cons = readJson(join(idir, "constraint.json"));
    const spec = readJson(join(idir, "clinvar_gene_spectrum.json"));
    const am = readJson(join(idir, "alphamissense_gene.json"));
    if (cons || spec || am) {
      const CF = Object.fromEntries((cons?.f ?? []).map((k, i) => [k, i]));
      // seven-factor view: protein family (UniProt/InterPro/Pfam/PANTHER) and tissue (HPA) per gene, in the same shards
      const fam = readJson(join(dataRoot, "derived", "features", "gene_families.json"));
      const tis = readJson(join(dataRoot, "derived", "features", "gene_tissue.json"));
      const FF = Object.fromEntries((fam?.f ?? []).map((k, i) => [k, i]));
      const genesAll = new Set([...Object.keys(cons?.genes ?? {}), ...Object.keys(spec?.genes ?? {}), ...Object.keys(am?.genes ?? {}), ...Object.keys(fam?.genes ?? {}), ...Object.keys(tis?.genes ?? {})]);
      const r3 = (x) => (typeof x === "number" ? Math.round(x * 1000) / 1000 : null);
      writeShards(
        join(webRoot, "public", "data", "derived", "web", "factors"),
        [...genesAll].map((g) => {
          const c = cons?.genes?.[g];
          const sp = spec?.genes?.[g];
          const a = am?.genes?.[g];
          const f = fam?.genes?.[g];
          const t = tis?.genes?.[g];
          return [
            g,
            {
              pli: c ? r3(c[CF.pLI]) : null,
              loeuf: c ? r3(c[CF.LOEUF]) : null,
              misz: c ? r3(c[CF.mis_z]) : null,
              am: a ? r3(a[0]) : null,
              n: sp?.n ?? 0,
              c: sp?.c ?? null,
              ...(f ? { uni: f[FF.uniprot] ?? null, len: f[FF.length] ?? null, panther: f[FF.panther_family] ?? [], ipr: f[FF.interpro_family] ?? [], pfam: f[FF.pfam] ?? [] } : {}),
              ...(t ? { hpa: t[0] ?? null, tis: t[1] ?? {} } : {}),
            },
          ];
        }),
      );
      console.log(`[sync-data] wrote web/factors shards for ${genesAll.size} genes`);
    }
    {
      const mdir = join(webRoot, "public", "data", "derived", "global", "mechanism");
      const gd = readJson(join(dataRoot, "derived", "direction", "gene_direction.json"));
      const cls = {};
      if (existsSync(mdir))
        for (const f of readdirSync(mdir).filter((x) => x.endsWith(".json"))) {
          const sh = readJson(join(mdir, f));
          for (const [id, e] of Object.entries(sh?.d ?? {})) {
            const c = [...new Set((e.mechanisms ?? []).map((m) => m.class).filter(Boolean))];
            if (c.length) cls[id] = { c };
          }
        }
      for (const [id, genes] of Object.entries(gd?.by_disease ?? {})) {
        const dirs = [...new Set(Object.values(genes).map((x) => x.direction).filter(Boolean))];
        if (dirs.length) (cls[id] ??= {}).d = dirs.length === 1 ? dirs[0] : "mixed";
      }
      writeFileSync(join(webRoot, "public", "data", "derived", "web", "mechclass.json"), JSON.stringify(cls));
      console.log(`[sync-data] wrote web/mechclass.json (${Object.keys(cls).length} diseases with a mechanism class or direction)`);
    }
    if (existsSync(join(idir, "primekg_eval.json"))) copyJson(idir, join(webRoot, "public", "data", "derived", "ingest"), ["primekg_eval.json"]);
  }
  // direction layer (data/derived/direction, eval.md section 6), slimmed to what the UI flag needs: curated
  // therapies (direction + direct gene targets), atlas disease directions and variant-group sides
  {
    const ddir = join(dataRoot, "derived", "direction");
    const gd = readJson(join(ddir, "gene_direction.json"));
    const dd = readJson(join(ddir, "drug_direction.json"));
    if (gd && dd) {
      const therapies = {};
      for (const [id, t] of Object.entries(dd.curated ?? {}))
        if ((t.direction === "increase" || t.direction === "decrease") && t.targets?.length) therapies[id] = { d: t.direction, t: t.targets, b: t.basis ?? null };
      const diseases = {};
      for (const [id, x] of Object.entries(gd.atlas_graph ?? {})) diseases[id] = { g: x.gene, d: x.direction ?? null };
      const vgs = {};
      for (const [id, x] of Object.entries(gd.atlas_variant_groups ?? {})) {
        const sides = [...new Set((x.sides ?? []).map((q) => q.side))];
        vgs[id] = { g: x.gene, d: sides.length === 1 ? sides[0] : sides.length ? "mixed" : null };
      }
      mkdirSync(join(webRoot, "public", "data", "derived", "web"), { recursive: true });
      writeFileSync(join(webRoot, "public", "data", "derived", "web", "direction.json"), JSON.stringify({ generated: gd.generated ?? null, therapies, diseases, vgs }));
      console.log(`[sync-data] direction: ${Object.keys(therapies).length} therapies with a direct target, ${Object.keys(diseases).length} diseases, ${Object.keys(vgs).length} variant groups`);
    }
  }
  const list = (dir) => (existsSync(dir) ? readdirSync(dir).filter((x) => x.endsWith(".json")).sort() : []);
  const available = {
    generated: new Date().toISOString().slice(0, 10),
    population: list(join(webRoot, "public", "data", "derived", "population")),
    scale: existsSync(join(webRoot, "public", "data", "derived", "web", "scale", "0.json")),
    dismech: existsSync(join(webRoot, "public", "data", "derived", "global", "dismech", "0.json")),
    dismech_snippets: existsSync(join(webRoot, "public", "data", "derived", "web", "dismech_snippets", "0.json")),
    mechanism: existsSync(join(webRoot, "public", "data", "derived", "global", "mechanism", "0.json")),
    groups: existsSync(join(webRoot, "public", "data", "derived", "global", "groups.json")),
    sequences: list(join(webRoot, "public", "data", "derived", "sequences")).map((f) => f.replace(/\.json$/, "")),
    variant_positions: existsSync(join(webRoot, "public", "data", "derived", "variant_positions.json")),
    eval: existsSync(join(webRoot, "public", "data", "derived", "eval.json")),
    testing_options: existsSync(join(webRoot, "public", "data", "curated", "testing_options.json")),
    clinvar_full: existsSync(join(webRoot, "public", "data", "derived", "web", "clinvar_genes.json")),
    factors: existsSync(join(webRoot, "public", "data", "derived", "web", "factors", "0.json")),
    primekg_eval: existsSync(join(webRoot, "public", "data", "derived", "ingest", "primekg_eval.json")),
    direction: existsSync(join(webRoot, "public", "data", "derived", "web", "direction.json")),
    eval_direction: existsSync(join(webRoot, "public", "data", "derived", "eval_direction.json")),
    similar: existsSync(join(webRoot, "public", "data", "derived", "global", "similar", "0.json")),
    contacts: existsSync(join(webRoot, "public", "data", "derived", "contacts", "orgs.json")) || existsSync(join(webRoot, "public", "data", "derived", "contacts", "trials.json")),
  };
  mkdirSync(join(webRoot, "public", "data", "derived", "web"), { recursive: true });
  writeFileSync(join(webRoot, "public", "data", "derived", "web", "available.json"), JSON.stringify(available, null, 2) + "\n");
}

const aiSrc = join(dataRoot, "ai");
if (existsSync(aiSrc)) {
  const aiDest = join(webRoot, "public", "data", "ai");
  mkdirSync(aiDest, { recursive: true });
  let n = 0;
  for (const f of readdirSync(aiSrc)) {
    if (f.endsWith(".json")) {
      copyFileSync(join(aiSrc, f), join(aiDest, f));
      n++;
    }
  }
  console.log(`[sync-data] copied ${n} precomputed AI file(s) from ../data/ai`);
}

// public/data/ai/index.json lists the precomputed AI files that exist, so the app never probes
// for missing ones (each probe would log a 404 in the browser console)
{
  const aiDir = join(webRoot, "public", "data", "ai");
  mkdirSync(aiDir, { recursive: true });
  const files = readdirSync(aiDir)
    .filter((f) => f.endsWith(".json") && f !== "index.json")
    .sort();
  writeFileSync(join(aiDir, "index.json"), JSON.stringify({ generated: new Date().toISOString().slice(0, 10), files }, null, 2) + "\n");
  console.log(`[sync-data] public/data/ai/index.json lists ${files.length} precomputed AI file(s)`);
}
