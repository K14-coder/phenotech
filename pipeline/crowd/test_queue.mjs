#!/usr/bin/env node
/**
 * End-to-end test of the research queue against a LOCAL dev server using the JSON FILE store only.
 * A fake extractor stands in for the model (it copies real sentences out of the packet's abstracts),
 * so no OpenAI call is made.
 *
 *   node pipeline/crowd/test_queue.mjs [--server http://127.0.0.1:3000] [--keep]
 *
 * Checks: two concurrent volunteers get different diseases; forged / out-of-packet / multi-sentence /
 * malformed claims are rejected while verbatim ones are accepted; an expired lease is finalised lazily on
 * the next claim and the disease returns to the TOP of the queue with its gaps; "I'm done" requeues;
 * worker tokens work and anonymous calls are refused. Creates three throwaway accounts and deletes them
 * at the end (and the queue file web/.data/queue.json unless --keep).
 */
import { randomBytes } from 'node:crypto';
import { open, readFile, rename, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const QFILE = path.join(ROOT, 'web', '.data', 'queue.json');
const args = process.argv.slice(2);
const SERVER = (args.includes('--server') ? args[args.indexOf('--server') + 1] : 'http://127.0.0.1:3000').replace(/\/$/, '');
const KEEP = args.includes('--keep');
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(SERVER)) throw new Error('This test only runs against a local dev server.');

let failures = 0;
const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}

class Client {
  constructor(label) {
    this.label = label;
    this.cookie = '';
  }
  async call(route, method = 'GET', body, headers = {}) {
    const r = await fetch(`${SERVER}${route}`, {
      method,
      headers: {
        origin: SERVER,
        ...(this.cookie ? { cookie: this.cookie } : {}),
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const set = r.headers.getSetCookie?.() ?? [];
    for (const c of set) if (c.startsWith('atlas_session=')) this.cookie = c.split(';')[0];
    const j = await r.json().catch(() => ({}));
    return { status: r.status, body: j };
  }
}

async function signup(label) {
  const c = new Client(label);
  const email = `rq-test-${randomBytes(5).toString('hex')}@example.test`;
  const password = randomBytes(18).toString('base64url');
  const r = await c.call('/api/account/signup', 'POST', { email, password, role: 'researcher' });
  if (r.status !== 200) throw new Error(`signup failed for ${label}: ${r.status} ${JSON.stringify(r.body)}`);
  return c;
}

// ---- fake extractor: real sentences from the packet's abstracts ----
const BAD_ABBR = /\b(e\.g|i\.e|et al|vs|cf|Fig|approx|ca|No|Ref|sp|spp)\.|\b[A-Z]\.\s/;
function sentences(abstract) {
  return abstract
    .split(/(?<=[.!?])\s+(?=[A-Z(])/)
    .map((s) => s.trim())
    .filter((s) => s.split(/\s+/).length >= 8 && /[.!?]$/.test(s) && !BAD_ABBR.test(s));
}
function fakeExtract(packet, { mechanism = 2, phenotypes = 1, groups = 1 } = {}) {
  const claims = [];
  const research_groups = [];
  const pool = packet.abstracts.flatMap((a) => sentences(a.abstract).map((s) => ({ pmid: a.pmid, s })));
  const base = { study_type: 'cohort', species: 'human', certainty: 'suggested', negated: false, therapy_stage: null };
  pool.slice(0, mechanism).forEach(({ pmid, s }) =>
    claims.push({ ...base, subject: packet.disease.name, relation: 'driven_by', object: 'loss of function', mechanism_class: 'loss_of_function', quote: s, pmid }),
  );
  pool.slice(mechanism, mechanism + phenotypes).forEach(({ pmid, s }, i) =>
    claims.push({ ...base, subject: packet.disease.name, relation: 'has_phenotype', object: `feature ${i + 1}`, mechanism_class: null, quote: s, pmid }),
  );
  for (const a of packet.abstracts) {
    const sa = a.senior_authors.find((x) => x.affiliation && x.affiliation.length >= 12);
    if (sa && research_groups.length < groups) research_groups.push({ pmid: a.pmid, senior_author: sa.name, affiliation: sa.affiliation });
  }
  return { claims, research_groups, pool };
}

// ---- direct edit of the file store (respecting its lock) to simulate an expired lease ----
async function withQueueFile(fn) {
  const lock = `${QFILE}.lock`;
  for (let i = 0; ; i += 1) {
    try {
      const h = await open(lock, 'wx');
      await h.close();
      break;
    } catch (e) {
      if (e.code !== 'EEXIST' || i > 500) throw e;
      await new Promise((r) => setTimeout(r, 20));
    }
  }
  try {
    const db = JSON.parse(await readFile(QFILE, 'utf8'));
    fn(db);
    await writeFile(`${QFILE}.test.tmp`, JSON.stringify(db));
    await rename(`${QFILE}.test.tmp`, QFILE);
  } finally {
    await rm(lock, { force: true });
  }
}

async function main() {
  const probe = await new Client('probe').call('/api/account');
  if (probe.body.mode !== 'file') throw new Error(`The dev server must use the FILE store (got "${probe.body.mode}"). Refusing to run.`);
  try {
    await stat(QFILE);
    throw new Error(`${QFILE} already exists; move it away first so the test starts from a clean queue.`);
  } catch (e) {
    if (e.code !== 'ENOENT') throw e;
  }

  const anon = await new Client('anon').call('/api/queue/claim', 'POST', {});
  check('anonymous claim is refused', anon.status === 401, `HTTP ${anon.status}`);

  const users = [];
  try {
    for (const label of ['A', 'B', 'C']) users.push(await signup(label));
    await scenario(...users);
  } finally {
    // always remove the throwaway accounts that were created
    for (const u of users) {
      await u.call('/api/queue/token', 'DELETE');
      const d = await u.call('/api/account', 'DELETE');
      check(`throwaway account ${u.label} deleted`, d.status === 200);
    }
    if (!KEEP) await rm(QFILE, { force: true });
  }
  console.log(`\n${results.length - failures}/${results.length} checks passed${KEEP ? '' : '; queue file removed'}.`);
  process.exit(failures ? 1 : 0);
}

async function scenario(A, B, C) {

  // 1. two concurrent volunteers
  const t0 = Date.now();
  const [ra, rb] = await Promise.all([A.call('/api/queue/claim', 'POST', {}), B.call('/api/queue/claim', 'POST', {})]);
  const pa = ra.body.packet;
  const pb = rb.body.packet;
  check('A and B both got a packet', !!pa && !!pb, `HTTP ${ra.status}/${rb.status} in ${Date.now() - t0} ms ${ra.body.error ?? ''} ${rb.body.error ?? ''}`);
  if (!pa || !pb) throw new Error('cannot continue');
  check('concurrent volunteers get different diseases', pa.disease.id !== pb.disease.id, `${pa.disease.id} vs ${pb.disease.id}`);
  check('packet has PubMed abstracts', pa.abstracts.length > 0 && pa.abstracts.length <= 15, `${pa.abstracts.length} abstracts, query ${pa.query.slice(0, 80)}…`);
  check('packet lists the 6-item checklist, all missing', pa.checklist.length === 6 && pa.missing.length === 6);
  check('lease is 7 hours', Math.abs(new Date(pa.lease.expiresAt) - new Date(pa.lease.claimedAt) - 7 * 3600_000) < 5000);
  const again = await A.call('/api/queue/claim', 'POST', {});
  check('claiming again returns the same lease (resume)', again.body.resumed === true && again.body.packet?.disease.id === pa.disease.id);

  // 2. verification
  const { claims, research_groups, pool } = fakeExtract(pa);
  const real = pool[0];
  const forged = { ...claims[0], quote: real.s.replace(/\b(\w{5,})\b/, '$1x') };
  const outside = { ...claims[0], pmid: '1' };
  const multi = pool.length > 4 && pool[3].pmid === pool[4].pmid ? { ...claims[0], quote: `${pool[3].s} ${pool[4].s}` } : null;
  const badSchema = { ...claims[0], relation: 'cures' };
  const extra = { ...claims[0], email: 'x@example.test' };
  const noMech = { ...claims[0], mechanism_class: null };
  const forgedGroup = research_groups[0] ? { ...research_groups[0], senior_author: 'Invented Person' } : null;
  const subA = await A.call('/api/queue/submit', 'POST', {
    token: pa.lease.token,
    model: 'fake-extractor',
    claims: [...claims, forged, outside, ...(multi ? [multi] : []), badSchema, extra, noMech],
    research_groups: [...research_groups, ...(forgedGroup ? [forgedGroup] : [])],
  });
  const reasons = (subA.body.rejected ?? []).map((r) => r.reason);
  check('verbatim claims accepted', subA.body.accepted === claims.length, `${subA.body.accepted} of ${claims.length}`);
  check('research group (senior author + affiliation) accepted', subA.body.acceptedGroups === research_groups.length, `${subA.body.acceptedGroups} of ${research_groups.length}`);
  check('forged quote rejected', reasons.some((r) => r.includes('not a verbatim sentence')), reasons.find((r) => r.includes('verbatim')));
  check('PMID outside the packet rejected', reasons.some((r) => r.includes('not in this task')));
  if (multi) check('two-sentence quote rejected', reasons.some((r) => r.includes('more than one sentence')));
  check('unknown relation rejected (schema)', reasons.some((r) => r.includes('relation is not one of')));
  check('extra field rejected (schema)', reasons.some((r) => r.includes('unexpected field')));
  check('driven_by without mechanism_class rejected', reasons.some((r) => r.includes('need a mechanism_class')));
  if (forgedGroup) check('invented senior author rejected', reasons.some((r) => r.includes('not a senior')));
  const mech = subA.body.checklist?.find((c) => c.id === 'mechanism');
  check('checklist ticks: mechanism 2/2 after two verbatim quotes', mech?.done === true, JSON.stringify(mech));
  const dup = await A.call('/api/queue/submit', 'POST', { token: pa.lease.token, model: 'fake-extractor', claims: claims.slice(0, 1), research_groups: [] });
  check('resubmitting the same claim counts as a duplicate, not credit', dup.body.duplicates === 1 && dup.body.accepted === 0);
  const wrongToken = await B.call('/api/queue/submit', 'POST', { token: pa.lease.token, model: 'x', claims: claims.slice(0, 1) });
  check("B cannot submit to A's lease", wrongToken.status === 409, `HTTP ${wrongToken.status}`);

  // 3. lease expiry -> lazy sweep on the next claim -> back to the TOP with gaps
  await withQueueFile((db) => {
    db.z['rq:leases'][pa.disease.id] = Date.now() - 1000;
    const k = `rq:lease:${pa.disease.id}`;
    const lease = JSON.parse(db.kv[k].v);
    lease.expiresAt = Date.now() - 1000;
    db.kv[k].v = JSON.stringify(lease);
  });
  const lateA = await A.call('/api/queue/submit', 'POST', { token: pa.lease.token, model: 'x', claims: claims.slice(0, 1) });
  check('submitting after the lease expired is refused', lateA.status === 410, `HTTP ${lateA.status}`);
  const rc = await C.call('/api/queue/claim', 'POST', {});
  const pc = rc.body.packet;
  check('next claim gets the expired, incomplete disease first (top of queue)', pc?.disease.id === pa.disease.id, `${pc?.disease.id}`);
  check('round 2 packet lists the gaps', pc?.lease.round === 2 && pc.missing.length > 0 && !pc.missing.includes('mechanism'), `missing: ${pc?.missing.join(', ')}`);
  check('round 2 packet shows the previous round', pc?.previousRounds?.[0]?.reason === 'expired' && pc.previousRounds[0].accepted > 0);
  const usedBefore = new Set(pa.abstracts.map((a) => a.pmid));
  check('round 2 brings different abstracts', pc ? pc.abstracts.every((a) => !usedBefore.has(a.pmid)) : false, `${pc?.abstracts.length} new`);

  // 4. "I'm done" with gaps -> requeued at the top, listed as returning
  const bClaims = fakeExtract(pb, { mechanism: 1, phenotypes: 0, groups: 0 }).claims;
  await B.call('/api/queue/submit', 'POST', { token: pb.lease.token, model: 'fake-extractor', claims: bClaims });
  const db = await B.call('/api/queue/done', 'POST', { token: pb.lease.token });
  check('"I\'m done" with gaps requeues the disease', db.body.status === 'queued', `${db.body.status}, missing ${db.body.missing?.join(', ')}`);
  const st = (await C.call('/api/queue/stats')).body;
  check('stats: requeued disease is first in "next 20" with its gaps', st.next[0]?.id === pb.disease.id && st.next[0].returning && st.next[0].gaps?.length > 0);
  check('stats: claims verified counted', st.claimsVerified >= claims.length + bClaims.length, `${st.claimsVerified} claims, ${st.groupsVerified} groups, ${st.rejected} rejected`);
  check('stats: leaderboard shows handles only', st.leaderboard.length >= 2 && st.leaderboard.every((r) => Object.keys(r).join() === 'handle,verified'));
  check('stats: one disease being researched now (C)', st.leasedNow === 1, `${st.leasedNow}`);
  const meA = (await A.call('/api/queue/stats')).body.me;
  check('per-volunteer counts kept', meA.accepted === claims.length + research_groups.length && meA.rejected >= 6 && meA.duplicates === 1, JSON.stringify(meA));

  // 5. public disease view (the /d/ block)
  const dv = (await new Client('anon').call(`/api/queue/disease/${encodeURIComponent(pa.disease.id)}`)).body;
  check('/api/queue/disease shows accepted claims with the unreviewed label', dv.claims?.length === claims.length && dv.claims.every((c) => c.status.includes('unreviewed')));

  // 6. worker token
  const tok = await C.call('/api/queue/token', 'POST', {});
  const viaTok = await new Client('worker').call('/api/queue/task', 'GET', undefined, { authorization: `Bearer ${tok.body.token}` });
  check('worker token authenticates as the volunteer', viaTok.body.packet?.disease.id === pc?.disease.id);
  const badTok = await new Client('worker').call('/api/queue/claim', 'POST', {}, { authorization: `Bearer rqw_${'x'.repeat(40)}` });
  check('unknown worker token refused', badTok.status === 401);
  const crossSite = await new Client('evil').call('/api/queue/claim', 'POST', {}, { origin: 'https://evil.example', cookie: C.cookie });
  check('cross-site POST with a session cookie refused', crossSite.status === 403, `HTTP ${crossSite.status}`);

  // 7. finish C, then clean up
  const dc = await C.call('/api/queue/done', 'POST', { token: pc.lease.token });
  check('C hands back (no submissions: still incomplete, requeued)', dc.body.status === 'queued');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
