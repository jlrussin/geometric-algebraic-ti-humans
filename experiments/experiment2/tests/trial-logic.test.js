/**
 * Tests of the question generation (js/trial-logic.js), the configuration and its checks
 * (js/config.js), the seeded streams (js/seeded-rng.js), the item tables (js/item-tables.js),
 * the participant-facing text that depends on the configuration (js/copy.js), the URL parameter
 * (js/mode.js), the saved document and rows (js/save.js), and the design constants that the
 * paper reports.
 *
 * Run from the repository root:
 *   node --test experiments/experiment2/tests/*.test.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  CONFIG, CONDITIONS, validateConfig, framesToMs, worldSlotPairDemand,
} from '../js/config.js';
import { loadStimuli, STIMULUS_PATHS } from '../js/item-tables.js';
import { makeStream, hashString, mulberry32 } from '../js/seeded-rng.js';
import * as mode from '../js/mode.js';
import {
  buildSession, mirrorTertilePicks, sampleSkeleton, assignKnowledgeDistances, assignBlocks,
  assignSides, assignQueryItems, dealContextItems, isBalancedOrdering, sampleShuffledOrdering,
  sampleLineOrderDeck, lineOrderStats, isAcceptedLineOrder, sequenceBlock, scoreResponse,
  renderStatement, canonicalJson, orderingStats, shuffleBounds, resolveAssignmentRow, shuffled,
} from '../js/trial-logic.js';
import {
  instructions, instructionExample, mainIntro, breakScreen, consent, question,
} from '../js/copy.js';
import {
  TASK_PHASES, buildInitialDocument, globalTrialProperties, finalizeTrialRow,
  planMetadata,
} from '../js/save.js';

const { tables } = await loadStimuli();
const ASSIGNMENTS = JSON.parse(
  await readFile(new URL('../data/assignments.json', import.meta.url), 'utf8'),
).assignments;
const clone = (x) => JSON.parse(JSON.stringify(x));
const withQ = (cfg, q) => ({ ...clone(cfg), mainQuestionCount: q });
const CFG = CONFIG;
const CFG36 = withQ(CFG, 36);
const N = CONFIG.slotCount;
const D = N - 3;
const range = (lo, hi) => Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
const countBy = (xs, f) => xs.reduce((mm, x) => mm.set(f(x), (mm.get(f(x)) || 0) + 1), new Map());
const row = (id, condition) => ({ assignment_id: id, condition });
const slotTable = (domainId) => tables.domains.find((d) => d.domain_id === domainId).slot_tables['9'];
const eligibleIds = (domainId) => slotTable(domainId)
  .map((s) => s.items.filter((it) => it.eligible).map((it) => it.item_id));
const refShuffle = (rng, arr) => {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

function allOrders(n) {
  const out = [];
  const rec = (prefix, rest) => {
    if (!rest.length) { out.push(prefix); return; }
    rest.forEach((v, i) => rec([...prefix, v], [...rest.slice(0, i), ...rest.slice(i + 1)]));
  };
  rec([], range(1, n));
  return out;
}

// --- seeded-rng, mode, config -------------------------------------------------------

test('makeStream: deterministic per (assignmentId, label), independent across labels', () => {
  const a = makeStream(7, 'orderings'); const b = makeStream(7, 'orderings'); const c = makeStream(7, 'lines');
  const xs = range(1, 5).map(() => a());
  assert.deepEqual(xs, range(1, 5).map(() => b()));
  assert.notDeepEqual(xs, range(1, 5).map(() => c()));
  const ref = mulberry32(hashString('7:orderings'));
  assert.deepEqual(xs, range(1, 5).map(() => ref()));
  assert.ok(xs.every((x) => x >= 0 && x < 1));
});

async function importModeWith(search) {
  globalThis.window = { location: { search } };
  try {
    // A fresh module per URL.
    return await import(`../js/mode.js?case=${encodeURIComponent(search)}`);
  } finally {
    delete globalThis.window;
  }
}

test('mode.js: ?assignment=N is a row number; absent is null; anything else is an error', async () => {
  assert.equal(mode.ASSIGNMENT_ID, null, 'no window in Node');
  assert.equal((await importModeWith('?assignment=12')).ASSIGNMENT_ID, 12);
  assert.equal((await importModeWith('?assignment=0')).ASSIGNMENT_ID, 0);
  for (const none of ['', '?other=3']) assert.equal((await importModeWith(none)).ASSIGNMENT_ID, null, none);
  for (const bad of ['?assignment=', '?assignment=-3', '?assignment=12x', '?assignment=1.0', '?assignment=12%20', '?assignment=x']) {
    await assert.rejects(importModeWith(bad), /\?assignment must be a row number/, bad);
  }
  assert.equal(typeof globalThis.window, 'undefined');
});

test('framesToMs: frame counts at 60 Hz', () => {
  assert.equal(framesToMs(48), 800);
  assert.equal(framesToMs(30), 500);
  assert.equal(framesToMs(24), 400);
});

test('validateConfig: passes on CONFIG and at 36 questions; fails each of rules 1-11', () => {
  assert.equal(validateConfig(CFG, tables), true);
  assert.equal(validateConfig(CFG36, tables), true);
  const cases = {
    1: (c) => { c.slotCount = 8; },
    2: (c) => { c.mainQuestionCount = 30; },
    3: (c) => { c.mainQuestionCount = 60; },
    4: (c) => { c.domains.instructions = c.domains.main; },
    5: null,
    6: null,
    7: (c) => { c.itemTableVersion = 'other'; },
    8: (c) => { c.instructionExample.oneStepQuery = [8, 9]; },
    9: (c) => { c.shuffle.perDistanceAgreeRange = [0.75, 0.25]; },
    10: (c) => { c.timing.confirmationMinFrames = 60 * 61; },
    11: (c) => { c.maxRun.correctSide = 0; },
  };
  for (const [id, mutate] of Object.entries(cases)) {
    const cfg = clone(CFG);
    let t = tables;
    if (id === '5') {
      t = clone(tables);
      t.domains.find((d) => d.domain_id === 'object_size').slot_tables['9'][0].items[0].item_id = 'ant';
    } else if (id === '6') {
      t = clone(tables);
      t.domains.find((d) => d.domain_id === 'animal_weight').forbidden_adjacent_pairs.push(['ant', 'blue_whale']);
    } else mutate(cfg);
    assert.throws(() => validateConfig(cfg, t), (e) => e.message.includes(`[${id}]`), `rule ${id}`);
  }
  for (const q of [0, 6, 18, 84, 1.5]) assert.throws(() => validateConfig(withQ(CFG, q), tables), /\[2\]/, `Q ${q}`);
  for (const q of [12, 24, 36, 48]) {
    assert.equal(validateConfig({ ...withQ(CFG, q), breakEvery: Math.min(CFG.breakEvery, q / 2) }, tables), true, `Q ${q}`);
  }
  for (const b of [0, 1.5, CFG.mainQuestionCount]) {
    assert.throws(() => validateConfig({ ...clone(CFG), breakEvery: b }, tables), /breakEvery must be/);
  }
});

test('validateConfig rejects 60 main questions with the (2, 8) capacity message', () => {
  const err = (() => { try { validateConfig(withQ(CFG, 60), tables); } catch (e) { return e.message; } return ''; })();
  assert.match(err, /\[3\] mainQuestionCount 60/);
  assert.match(err, /\(2, 8\) needs 10 but has 3 × 3 = 9/);
  assert.match(err, /largest feasible count with these tables is 48/);
  // worldSlotPairDemand follows the skeleton: the picks at kd give x.
  const demand = worldSlotPairDemand(CFG);
  assert.equal(demand.get('2-8'), CFG.mainQuestionCount / D);
  assert.equal([...demand.values()].reduce((a, b) => a + b, 0), CFG.mainQuestionCount);
});

test('validateConfig: the instruction example (items, line order, query)', () => {
  const bad = (mutate, pattern) => {
    const cfg = clone(CFG);
    mutate(cfg.instructionExample);
    assert.throws(() => validateConfig(cfg, tables), (e) => e.message.includes('[8]') && pattern.test(e.message), pattern.toString());
  };
  bad((ex) => { [ex.itemIds[0], ex.itemIds[1]] = [ex.itemIds[1], ex.itemIds[0]]; }, /must be the world order/);
  bad((ex) => { ex.itemIds = ex.itemIds.slice(0, 8); }, /must list 9 item IDs/);
  bad((ex) => { ex.itemIds[0] = 'ant'; }, /not eligible/);
  bad((ex) => { ex.lineOrder = range(0, 7); }, /breaks the line-order rule/);
  bad((ex) => { ex.lineOrder = [0, 0, 1, 2, 3, 4, 5, 6]; }, /must order the statement indices/);
  bad((ex) => { ex.oneStepQuery = [7, 9]; }, /oneStepQuery must be/);
  bad((ex) => { ex.oneStepQuery = [1, 2]; }, /oneStepQuery must be/);
});

test('the item tables load, match CONFIG, and malformed files are rejected', async () => {
  assert.equal(STIMULUS_PATHS.itemTables, 'data/item_tables.json');
  assert.ok(tables.domains.some((d) => d.domain_id === CONFIG.domains.main));
  assert.ok(tables.domains.some((d) => d.domain_id === CONFIG.domains.instructions));
  const dir = await mkdtemp(join(tmpdir(), 'experiment2-'));
  const badPath = join(dir, 'bad.json');
  const t = clone(tables); t.domains[0].slot_tables['9'][0].items[0].name_chars = 99;
  await writeFile(badPath, JSON.stringify(t));
  await assert.rejects(loadStimuli({ itemTables: badPath }), /name_chars/);
  const t2 = clone(tables); t2.domains[0].forbidden_adjacent_pairs = [['ant']];
  await writeFile(badPath, JSON.stringify(t2));
  await assert.rejects(loadStimuli({ itemTables: badPath }), /forbidden_adjacent_pairs/);
});

// --- skeleton, real-world distances, blocks, sides ---------------------------------

test('mirrorTertilePicks and sampleSkeleton: deterministic at even m; the tertile rule', () => {
  // At m = 8 the picks at distance 1 are 2, 7, 3, 6, 4, 5, 2, 7 (every adjacent pair).
  assert.deepEqual(mirrorTertilePicks(makeStream(0, 'x'), N, 1, 8).map((p) => p.a), [2, 7, 3, 6, 4, 5, 2, 7]);
  for (const cfg of [CFG, CFG36]) {
    const m = cfg.mainQuestionCount / D;
    const ref = sampleSkeleton(makeStream(0, 'skeleton'), cfg);
    assert.equal(ref.m, m);
    for (let seed = 1; seed < 50; seed++) {
      assert.deepEqual(sampleSkeleton(makeStream(seed, 'skeleton'), cfg), ref, 'the same skeleton for everyone');
    }
    ref.picks.forEach((picks, i) => {
      const d = i + 1;
      assert.equal(picks.length, m);
      assert.ok(picks.every((p) => p.a >= 2 && p.a + d <= N - 1));
      // Mirror groups: every low pick is followed by its high mirror.
      picks.forEach((p, k) => {
        if (p.bin === 'low') assert.deepEqual(picks[k + 1], { a: N + 1 - p.a - d, bin: 'high' });
      });
      const mean = picks.reduce((s, p) => s + p.a + d / 2, 0) / m;
      assert.ok(Math.abs(mean - (N + 1) / 2) < 1e-12, `m=${m} d=${d}: mean midpoint ${mean}`);
    });
  }
  assert.throws(() => sampleSkeleton(makeStream(0, 's'), { ...CFG, mainQuestionCount: 50 }));
});

test('assignKnowledgeDistances: Latin incidence, agree/conflict labels, |r| bound, mirror split', () => {
  for (const cfg of [CFG, CFG36, withQ(CFG, 24)]) {
    const sk = sampleSkeleton(makeStream(0, 'skeleton'), cfg);
    const m = sk.m;
    for (let seed = 0; seed < 100; seed++) {
      const kn = assignKnowledgeDistances(makeStream(seed, 'knowledge'), sk, cfg);
      const L = kn.latin_square;
      for (let i = 0; i < D; i++) {
        assert.deepEqual([...L[i]].sort((a, b) => a - b), range(1, D));
        assert.deepEqual(L.map((r) => r[i]).sort((a, b) => a - b), range(1, D));
      }
      const base = kn.columns.slice(0, Math.min(m, D));
      const extras = kn.columns.slice(Math.min(m, D));
      assert.equal(new Set(base).size, base.length);
      assert.equal(new Set(extras).size, extras.length);
      assert.equal(kn.columns.length, m);
      const qs = kn.questions;
      assert.equal(qs.length, m * D);
      for (const key of ['d', 'kd']) {
        for (let v = 1; v <= D; v++) {
          const at = qs.filter((q) => q[key] === v);
          assert.equal(at.length, m);
          assert.equal(at.filter((q) => q.congruence === 'agree').length, m / 2, `${key}=${v}`);
        }
      }
      assert.ok(Math.abs(kn.r_dk) <= cfg.shuffle.maxAbsCorrDK + 1e-9);
      if (m === D) {
        assert.equal(kn.r_dk, 0);
        assert.equal(kn.draws, 1);
        assert.equal(new Set(qs.map((q) => `${q.d}|${q.kd}`)).size, D * D, 'm = D: every (d, kd) once');
      }
      if (m > D) assert.equal(new Set(qs.map((q) => `${q.d}|${q.kd}`)).size, D * D, 'm > D: every (d, kd) occurs');
      // Positions and world slots: the skeleton's multisets, split evenly over the mirror groups.
      for (const [key, pos] of [['d', 'a'], ['kd', 'x']]) {
        for (let v = 1; v <= D; v++) {
          const at = qs.filter((q) => q[key] === v);
          assert.deepEqual(at.map((q) => q[pos]).sort(), sk.picks[v - 1].map((p) => p.a).sort());
          const group = (a) => Math.min(a, N + 1 - a - v);
          const ag = countBy(at.filter((q) => q.congruence === 'agree'), (q) => group(q[pos]));
          const cf = countBy(at.filter((q) => q.congruence === 'conflict'), (q) => group(q[pos]));
          assert.deepEqual([...ag].sort(), [...cf].sort(), `${key}=${v} mirror split`);
        }
      }
      assert.ok(qs.every((q) => q.x >= 2 && q.x + q.kd <= N - 1 && q.a >= 2 && q.a + q.d <= N - 1));
      assert.ok(qs.every((q, j) => j === 0 || q.d >= qs[j - 1].d), 'canonical order by d');
    }
  }
  // The first draws are the reference primitives on the same stream.
  const rng = makeStream(5, 'knowledge');
  const rowPerm = refShuffle(rng, range(0, D - 1));
  const colPerm = refShuffle(rng, range(0, D - 1));
  const symbols = refShuffle(rng, range(1, D));
  const kn = assignKnowledgeDistances(makeStream(5, 'knowledge'), sampleSkeleton(makeStream(5, 'skeleton'), CFG36), CFG36);
  assert.deepEqual(kn.latin_square, rowPerm.map((ri) => colPerm.map((ci) => symbols[(ri + ci) % D])));
});

test('assignBlocks and assignSides: 2 per (block, d); one left and one right; shuffled balance', () => {
  for (const cfg of [CFG, CFG36]) {
    const sk = sampleSkeleton(makeStream(0, 'skeleton'), cfg);
    const B = cfg.mainQuestionCount / (2 * D);
    for (let seed = 0; seed < 100; seed++) {
      const shuffledQs = assignKnowledgeDistances(makeStream(seed, 'knowledge'), sk, cfg).questions;
      const congruentQs = sk.picks.flatMap((picks, i) => picks.map((p) => ({ d: i + 1, kd: i + 1, congruence: 'agree', a: p.a, x: p.a })));
      for (const qs of [congruentQs, shuffledQs]) {
        const blocks = assignBlocks(makeStream(seed, 'blocks'), qs, cfg);
        const { sides } = assignSides(makeStream(seed, 'sides'), qs, blocks, cfg);
        for (let b = 1; b <= B; b++) {
          for (let d = 1; d <= D; d++) {
            const pair = qs.map((q, j) => j).filter((j) => blocks[j] === b && qs[j].d === d);
            assert.equal(pair.length, 2);
            assert.deepEqual(pair.map((j) => sides[j]).sort(), ['left', 'right']);
            if (qs === shuffledQs) assert.deepEqual(pair.map((j) => qs[j].congruence).sort(), ['agree', 'conflict']);
          }
        }
        if (qs === shuffledQs) {
          const agreeLeft = qs.map((q, j) => j).filter((j) => qs[j].congruence === 'agree' && sides[j] === 'left');
          for (let b = 1; b <= B; b++) assert.equal(agreeLeft.filter((j) => blocks[j] === b).length, D / 2);
          for (let d = 1; d <= D; d++) {
            const n = agreeLeft.filter((j) => qs[j].d === d).length;
            assert.ok(n === Math.floor(B / 2) || n === Math.ceil(B / 2), `B=${B} d=${d}: ${n}`);
          }
        }
      }
    }
  }
});

// --- items ----------------------------------------------------------------------------

test('assignQueryItems: a tight 3 × 3 slot pair uses distinct pairs with counts within 1', () => {
  const elig = range(1, N).map((s) => ['a', 'b', 'c'].map((c) => `s${s}${c}`));
  for (const k of [8, 9]) {
    for (let seed = 0; seed < 50; seed++) {
      const qs = range(1, k).map(() => ({ kd: 6, x: 2 }));
      const { pairs, queryCounts } = assignQueryItems(makeStream(seed, 'items'), qs, elig);
      assert.equal(new Set(pairs.map((p) => `${p.low}|${p.high}`)).size, k, 'every pair distinct');
      assert.ok(pairs.every((p) => elig[1].includes(p.low) && elig[7].includes(p.high)));
      for (const s of [2, 8]) {
        const cs = elig[s - 1].map((id) => queryCounts.get(id) || 0).sort();
        assert.deepEqual(cs, k === 9 ? [3, 3, 3] : [2, 3, 3], `k=${k} slot ${s}`);
      }
    }
  }
  assert.throws(() => assignQueryItems(makeStream(0, 'items'), range(1, 10).map(() => ({ kd: 6, x: 2 })), elig),
    /ran out of distinct item pairs/);
});

test('assignQueryItems and dealContextItems on the main domain: unique pairs, ±1 query counts, ⌊Q/n⌋/⌈Q/n⌉ totals', () => {
  const elig = eligibleIds(CFG.domains.main);
  for (const cfg of [CFG, CFG36]) {
    const Q = cfg.mainQuestionCount;
    const sk = sampleSkeleton(makeStream(0, 'skeleton'), cfg);
    for (let seed = 0; seed < 100; seed++) {
      const qs = assignKnowledgeDistances(makeStream(seed, 'knowledge'), sk, cfg).questions;
      const rng = makeStream(seed, 'items');
      const { pairs, queryCounts } = assignQueryItems(rng, qs, elig);
      assert.equal(new Set(pairs.map((p) => [p.low, p.high].sort().join('|'))).size, Q);
      for (let s = 2; s <= N - 1; s++) {
        const cs = elig[s - 1].map((id) => queryCounts.get(id) || 0);
        assert.ok(Math.max(...cs) - Math.min(...cs) <= 1, `slot ${s}: ${cs}`);
      }
      const items = dealContextItems(rng, qs, pairs, elig);
      const totals = new Map();
      items.forEach((bySlot, j) => {
        bySlot.forEach((id, i) => { assert.ok(elig[i].includes(id)); totals.set(id, (totals.get(id) || 0) + 1); });
        assert.equal(bySlot[qs[j].x - 1], pairs[j].low);
        assert.equal(bySlot[qs[j].x + qs[j].kd - 1], pairs[j].high);
      });
      elig.forEach((ids) => ids.forEach((id) => {
        const t = totals.get(id);
        assert.ok(t === Math.floor(Q / ids.length) || t === Math.ceil(Q / ids.length), `${id}: ${t}`);
      }));
    }
  }
});

test('dealContextItems: forced ceilings and impossible query counts', () => {
  // Slot 2 has 2 items; 3 questions query slot 2 with item "p" twice: Q = 4, ⌊Q/n⌋ = 2, so "p"
  // totals 2 or 3.
  const elig = range(1, N).map((s) => [`s${s}p`, `s${s}q`]);
  const qs = [{ kd: 1, x: 2 }, { kd: 1, x: 2 }, { kd: 2, x: 2 }, { kd: 1, x: 5 }];
  const pairs = [{ low: 's2p', high: 's3p' }, { low: 's2p', high: 's3q' }, { low: 's2q', high: 's4p' }, { low: 's5p', high: 's6p' }];
  const items = dealContextItems(makeStream(1, 'items'), qs, pairs, elig);
  for (let s = 1; s <= N; s++) {
    const c = countBy(items.map((r) => r[s - 1]), (x) => x);
    assert.ok([...c.values()].every((n) => n === 2), `slot ${s}: ${[...c]}`);
  }
  const over = [{ low: 's2p', high: 's3p' }, { low: 's2p', high: 's3q' }, { low: 's2p', high: 's4p' }, { low: 's5p', high: 's6p' }];
  assert.throws(() => dealContextItems(makeStream(1, 'items'), qs, over, elig), /leave no/);
});

// --- balanced shuffles ----------------------------------------------------------------

test('isBalancedOrdering: equals an independent enumeration of the balance rules, with inclusive bounds', () => {
  const sh = CONFIG.shuffle;
  const b = shuffleBounds(N, sh);
  assert.deepEqual([b.agreeLo, b.agreeHi, b.trueLo, b.trueHi], [15, 21, 3, 5]);
  // The balance rules written out from their definition: agreeing pairs within the agree range
  // of C(N, 2), true statements within (N - 1)/2 ± the deviation, no run of more than
  // maxSameDirectionRun statements in one direction, and at every distance 1..N - 3 the
  // agreeing fraction in range.
  const P = (N * (N - 1)) / 2;
  const passes = (o) => {
    let agree = 0;
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) if (o[i] < o[j]) agree++;
    const dirs = range(0, N - 2).map((c) => o[c] < o[c + 1]);
    const trueCount = dirs.filter(Boolean).length;
    let longest = 1;
    for (let c = 1, run = 1; c < dirs.length; c++) { run = dirs[c] === dirs[c - 1] ? run + 1 : 1; longest = Math.max(longest, run); }
    const fracOk = range(1, N - 3).every((d) => {
      const f = range(0, N - 1 - d).filter((i) => o[i] < o[i + d]).length / (N - d);
      return f >= sh.perDistanceAgreeRange[0] - 1e-9 && f <= sh.perDistanceAgreeRange[1] + 1e-9;
    });
    return agree / P >= sh.agreePairsFractionRange[0] - 1e-9 && agree / P <= sh.agreePairsFractionRange[1] + 1e-9
      && Math.abs(trueCount - (N - 1) / 2) <= sh.trueStatementsMaxDeviation && longest <= sh.maxSameDirectionRun && fracOk;
  };
  let accepted = 0;
  const hitAgree = new Set(); const hitTrue = new Set(); const hitFrac = new Set();
  for (const o of allOrders(N)) {
    const ok = isBalancedOrdering(o, CONFIG);
    if (ok !== passes(o)) assert.fail(`ordering ${o.join(',')}: module ${ok}, definition ${!ok}`);
    if (!ok) continue;
    accepted++;
    const s = orderingStats(o);
    hitAgree.add(s.agree_pairs); hitTrue.add(s.true_statements);
    for (let d = 1; d <= D; d++) hitFrac.add(s.agree_by_distance[d - 1] / (N - d));
  }
  assert.ok(accepted > 0);
  assert.ok(hitAgree.has(b.agreeLo) && hitAgree.has(b.agreeHi), 'agree-pair bounds are inclusive');
  assert.ok(hitTrue.has(b.trueLo) && hitTrue.has(b.trueHi), 'true-statement bounds are inclusive');
  assert.ok(hitFrac.has(sh.perDistanceAgreeRange[0]) && hitFrac.has(sh.perDistanceAgreeRange[1]), 'per-distance bounds are inclusive');
  assert.ok(!isBalancedOrdering(range(1, N), CONFIG));
});

test('orderingStats: congruent and reversed extremes', () => {
  const P = (N * (N - 1)) / 2;
  assert.deepEqual(orderingStats(range(1, N)), { agree_pairs: P, true_statements: N - 1, max_run: N - 1, agree_by_distance: range(1, N - 1).reverse() });
  const rev = orderingStats(range(1, N).reverse());
  assert.equal(rev.agree_pairs, 0); assert.equal(rev.true_statements, 0); assert.equal(rev.max_run, N - 1);
});

test('sampleShuffledOrdering: honors the queried slots and the balance rules; no query; throws past maxDraws', () => {
  const rng = makeStream(5, 'orderings');
  for (let i = 0; i < 50; i++) {
    const query = { a: 3, d: 2, slotAtA: 4 + (i % 3), slotAtAd: 2 };
    const { ordering, draws } = sampleShuffledOrdering(rng, query, CONFIG);
    assert.equal(ordering[2], query.slotAtA); assert.equal(ordering[4], 2);
    assert.ok(isBalancedOrdering(ordering, CONFIG) && draws >= 1);
  }
  assert.ok(isBalancedOrdering(sampleShuffledOrdering(rng, null, CONFIG).ordering, CONFIG));
  const tight = clone(CONFIG); tight.shuffle.maxDraws = 5;
  assert.throws(() => sampleShuffledOrdering(rng, { a: 2, d: 1, slotAtA: 3, slotAtAd: 3 }, tight));
});

// --- line order -----------------------------------------------------------------------

test('lineOrderStats: runs in both directions, adjacencies, tau', () => {
  assert.deepEqual(lineOrderStats([1, 2, 3, 4, 5, 6, 7, 8]), { chain_adjacencies: 7, max_in_order_run: 8, tau: 1 });
  assert.deepEqual(lineOrderStats([8, 7, 6, 5, 4, 3, 2, 1]), { chain_adjacencies: 7, max_in_order_run: 8, tau: -1 });
  const up = lineOrderStats([5, 6, 7, 1, 3, 8, 2, 4]);
  assert.equal(up.max_in_order_run, 3); assert.equal(up.chain_adjacencies, 2);
  const down = lineOrderStats([4, 3, 2, 8, 1, 6, 5, 7]);
  assert.equal(down.max_in_order_run, 3); assert.equal(down.chain_adjacencies, 3);
  assert.equal(lineOrderStats([3, 4, 5, 4]).max_in_order_run, 3);
  assert.equal(lineOrderStats([1, 2, 1, 2]).max_in_order_run, 2);
  const noRun = lineOrderStats([1, 3, 5, 7, 2, 4, 6, 8]);
  assert.equal(noRun.max_in_order_run, 1); assert.equal(noRun.chain_adjacencies, 0);
  assert.equal(lineOrderStats([2, 1, 4, 3]).tau, (4 - 2) / 6);
});

test('line-order rule: isAcceptedLineOrder equals an independent enumeration', () => {
  const lo = CONFIG.lineOrder;
  let viaModule = 0; let independent = 0;
  for (const s of allOrders(N - 1)) {
    if (isAcceptedLineOrder(s, CONFIG)) viaModule++;
    let chain = 0; let conc = 0; let best = 1;
    for (let i = 0; i + 1 < s.length; i++) chain += Math.abs(s[i + 1] - s[i]) === 1 ? 1 : 0;
    for (let i = 0; i < s.length; i++) for (let j = i + 1; j < s.length; j++) conc += Math.sign(s[j] - s[i]);
    for (let i = 0; i + 2 < s.length; i++) {
      const a = s[i + 1] - s[i]; const b = s[i + 2] - s[i + 1];
      if (Math.abs(a) === 1 && a === b) best = 3;
    }
    if (chain <= lo.maxChainAdjacencies && best <= lo.maxInOrderRun
      && Math.abs(conc / ((s.length * (s.length - 1)) / 2)) < lo.maxAbsTau) independent++;
  }
  assert.equal(viaModule, independent);
});

test('sampleLineOrderDeck: distinct accepted orders; throws past maxDraws', () => {
  const { deck, draws } = sampleLineOrderDeck(makeStream(9, 'lines'), CONFIG.mainQuestionCount, CONFIG);
  assert.equal(deck.length, CONFIG.mainQuestionCount);
  assert.equal(new Set(deck.map((x) => x.join())).size, deck.length);
  assert.ok(draws >= deck.length);
  assert.ok(deck.every((s) => isAcceptedLineOrder(s, CONFIG)));
  const tight = clone(CONFIG); tight.lineOrder.maxDraws = 3;
  assert.throws(() => sampleLineOrderDeck(makeStream(9, 'lines'), 18, tight));
});

// --- sequencing -----------------------------------------------------------------------

test('sequenceBlock: caps hold across the boundary; null when attempts run out', () => {
  const mk = (i, over = {}) => ({
    correct_answer_context: i % 2 ? 'left' : 'right', context_distance: 1 + (i % 6),
    query_congruence: i % 3 ? 'agree' : 'conflict', ...over,
  });
  const block = range(0, 11).map((i) => mk(i));
  const previous = range(0, 3).map((i) => mk(i, { correct_answer_context: 'left' }));
  const { sequence, attempts } = sequenceBlock(makeStream(1, 'sequence'), block, previous, CONFIG);
  assert.ok(sequence && attempts >= 1);
  const all = [...previous, ...sequence];
  for (const [key, max] of [['correct_answer_context', CONFIG.maxRun.correctSide], ['context_distance', CONFIG.maxRun.contextDistance]]) {
    let run = 1;
    for (let i = previous.length; i < all.length; i++) {
      run = all[i][key] === all[i - 1][key] ? run + 1 : 1;
      assert.ok(run <= max, `${key} run ${run}`);
    }
  }
  const impossible = range(0, 5).map((i) => mk(i, { context_distance: 1 }));
  assert.deepEqual(sequenceBlock(makeStream(1, 'sequence'), impossible, [], { ...CONFIG, sequenceMaxAttempts: 50 }),
    { sequence: null, attempts: 50 });
});

// --- text, scoring, canonical JSON, shuffle -------------------------------------------

test('renderStatement: articles and capitalization', () => {
  assert.equal(renderStatement('the horse', 'is heavier than', 'the dog'), 'The horse is heavier than the dog.');
  assert.equal(renderStatement('a haircut', 'takes longer than', 'an eye blink'), 'A haircut takes longer than an eye blink.');
  assert.equal(renderStatement('two thousand', 'is greater than', 'nine'), 'Two thousand is greater than nine.');
});

test('scoreResponse: congruent, agree and conflict questions, and timeouts', () => {
  const base = { query_left_item: 'L', query_right_item: 'R' };
  const rows = {
    congruent: { phase: 'main', correct_answer_context: 'left', knowledge_answer: 'left' },
    'shuffled agree': { phase: 'main', correct_answer_context: 'right', knowledge_answer: 'right' },
    'shuffled conflict': { phase: 'main', correct_answer_context: 'right', knowledge_answer: 'left' },
  };
  for (const [label, r0] of Object.entries(rows)) {
    const r = { ...base, ...r0 };
    for (const response of ['left', 'right']) {
      const s = scoreResponse({ ...r, response });
      assert.equal(s.chosen_item, response === 'left' ? 'L' : 'R');
      assert.equal(s.is_correct, response === r.correct_answer_context, label);
      assert.equal(s.is_knowledge_consistent, response === r.knowledge_answer, label);
    }
    assert.deepEqual(scoreResponse({ ...r, response: null }), { chosen_item: null, is_correct: false, is_knowledge_consistent: null }, label);
    for (const badResponse of [undefined, 'f', 'LEFT', '', 0]) {
      assert.throws(() => scoreResponse({ ...r, response: badResponse }), /response must be/, `${label} ${badResponse}`);
    }
  }
});

test('canonicalJson: sorted keys, no whitespace, JSON semantics', () => {
  assert.equal(canonicalJson({ b: 1, a: [3, { d: null, c: 'x' }], e: 'é"' }), '{"a":[3,{"c":"x","d":null}],"b":1,"e":"é\\""}');
  assert.equal(canonicalJson({ a: undefined, b: [undefined] }), '{"b":[null]}');
  assert.equal(canonicalJson([]), '[]');
  assert.equal(canonicalJson(true), 'true');
  assert.throws(() => canonicalJson({ a: NaN }));
  const obj = { z: 1, y: { x: 2, w: [1, 2] } };
  assert.deepEqual(JSON.parse(canonicalJson(obj)), obj);
});

test('shuffled: Fisher–Yates on a copy', () => {
  for (const n of [0, 1, 2, 5, 9]) {
    const input = range(1, n);
    const a = makeStream(3, `shuffle-test-${n}`);
    const b = makeStream(3, `shuffle-test-${n}`);
    assert.deepEqual(shuffled(a, input), refShuffle(b, input));
    assert.deepEqual(input, range(1, n));   // the input is not touched
  }
});

// --- whole sessions -------------------------------------------------------------------

const RECORD_KEYS = ['phase', 'trial_number', 'block_index', 'ordering_type', 'query_congruence', 'domain', 'relation_word',
  'context_distance', 'knowledge_distance', 'scale_position_bin', 'query_left_item', 'query_right_item', 'query_left_text',
  'query_right_text', 'query_left_context_position', 'query_right_context_position', 'query_left_slot', 'query_right_slot',
  'correct_answer_context', 'knowledge_answer', 'item_pair_key', 'context_ordering_json', 'context_slots_json',
  'statements_text_json', 'statements_char_count', 'line_order_json', 'path_line_positions_json', 'path_agree_links',
  'ordering_agree_pairs', 'ordering_true_statements', 'ordering_max_run', 'line_order_chain_adjacencies',
  'line_order_max_in_order_run', 'line_order_tau'];

test('buildSession: both conditions complete, deterministic, distinct; record shape; balance keys', async () => {
  for (const condition of CONDITIONS) {
    const a = await buildSession(row(11, condition), CFG, tables);
    const b = await buildSession(row(11, condition), CFG, tables);
    const c = await buildSession(row(12, condition), CFG, tables);
    assert.equal(a.schedule_sha256, b.schedule_sha256);
    assert.notEqual(a.schedule_sha256, c.schedule_sha256);
    assert.match(a.schedule_sha256, /^[0-9a-f]{64}$/);
    assert.equal(a.condition, condition);
    assert.equal(a.main.length, CFG.mainQuestionCount);
    assert.deepEqual(a.schedule, a.main.map((t) => t.record));
    for (const t of a.main) {
      assert.deepEqual(Object.keys(t.params), ['question_html', 'left_label', 'right_label', 'statements', 'deadline_ms',
        'confirmation_min_ms']);
      assert.deepEqual(Object.keys(t.record), RECORD_KEYS);
    }
    const main = a.main.map((t) => t.record);
    assert.ok(main.every((r) => r.phase === 'main' && r.ordering_type === condition && r.domain === CFG.domains.main));
    assert.deepEqual(main.map((r) => r.trial_number), range(1, CFG.mainQuestionCount));
    assert.equal(new Set(main.map((r) => r.item_pair_key)).size, CFG.mainQuestionCount, 'no query pair twice');
    const keys = Object.keys(a.balance_exactness).sort();
    const common = ['blocks', 'distance_counts', 'items_by_slot', 'knowledge_by_distance', 'knowledge_distance_counts',
      'line_orders_distinct', 'query_items_by_slot', 'query_pairs_unique', 'sides', 'skeleton'];
    assert.deepEqual(keys, (condition === 'shuffled' ? [...common, 'distance_by_knowledge_distance', 'mirror_split'] : common).sort());
    assert.equal(a.generation_stats.sequence_attempts.length, CFG.mainQuestionCount / (2 * D));
    if (condition === 'congruent') {
      assert.ok(main.every((r) => r.query_congruence === 'agree' && r.knowledge_distance === r.context_distance));
      assert.equal(a.generation_stats.latin_square_draws, 0);
    } else {
      assert.equal(main.filter((r) => r.query_congruence === 'conflict').length, CFG.mainQuestionCount / 2);
    }
    assert.equal(a.item_table_version, CFG.itemTableVersion);
  }
  await assert.rejects(buildSession(row(11, 'reversed'), CFG, tables), /condition must be/);
  await assert.rejects(buildSession({ assignment_id: 11 }, CFG, tables), /condition must be/);
  await assert.rejects(buildSession({ assignment_id: -1, condition: 'shuffled' }, CFG, tables), /assignment_id/);
});

test('buildSession: 36 questions; slot-table order does not change the questions', async () => {
  for (const condition of CONDITIONS) {
    const s = await buildSession(row(3, condition), CFG36, tables);
    assert.equal(s.main.length, 36);
    assert.equal(s.generation_stats.sequence_attempts.length, 3);
    if (condition === 'shuffled') {
      assert.equal(s.balance_exactness.sides, 'pm1', 'three blocks: agree-left per d is 1 or 2');
      assert.equal(s.balance_exactness.distance_by_knowledge_distance, 'exact', 'm = D: each (d, kd) once');
    }
  }
  const reordered = clone(tables);
  for (const d of reordered.domains) d.slot_tables['9'].reverse();
  assert.equal(validateConfig(CFG, reordered), true);
  for (const condition of CONDITIONS) {
    const a = await buildSession(row(5, condition), CFG, tables);
    const b = await buildSession(row(5, condition), CFG, reordered);
    assert.equal(a.schedule_sha256, b.schedule_sha256, `${condition}: slot-table order does not change the questions`);
  }
});

// --- assignment rows ------------------------------------------------------------------

test('resolveAssignmentRow: the table row by id (an id that is not a row throws), or a uniform draw', () => {
  const N0 = ASSIGNMENTS.length;
  const never = () => { throw new Error('rand must not be called'); };
  assert.deepEqual(resolveAssignmentRow(ASSIGNMENTS, 5, never), ASSIGNMENTS[5]);
  assert.deepEqual(resolveAssignmentRow(ASSIGNMENTS, N0 - 1, never), ASSIGNMENTS[N0 - 1]);
  for (const id of [N0, N0 + 3, -1, 1.5]) {
    assert.throws(() => resolveAssignmentRow(ASSIGNMENTS, id, never), /is not a row of data\/assignments\.json/, String(id));
  }
  for (const u of [0, 0.25, 0.999999]) {
    assert.deepEqual(resolveAssignmentRow(ASSIGNMENTS, null, () => u), ASSIGNMENTS[Math.floor(u * N0)]);
  }
  // Returned rows are copies.
  const any = resolveAssignmentRow(ASSIGNMENTS, null, () => 0.25);
  any.condition = 'x';
  assert.notEqual(ASSIGNMENTS[Math.floor(0.25 * N0)].condition, 'x');
  assert.throws(() => resolveAssignmentRow([], null, () => 0), /no rows/);
});

test('the assignment table: 1,000 rows, both conditions in every block of two', () => {
  assert.deepEqual(ASSIGNMENTS.map((r) => r.assignment_id), range(0, ASSIGNMENTS.length - 1));
  assert.ok(ASSIGNMENTS.every((r) => CONDITIONS.includes(r.condition)));
  for (let i = 0; i < ASSIGNMENTS.length; i += 2) {
    assert.deepEqual([ASSIGNMENTS[i].condition, ASSIGNMENTS[i + 1].condition].sort(), [...CONDITIONS].sort(), `rows ${i}-${i + 1}`);
  }
});

// --- the saved document ---------------------------------------------------------------

test('save: document root, row fields and the summary of the questions', async () => {
  const now = new Date('2026-10-01T12:34:56.789Z');
  const doc = buildInitialDocument({ assignmentId: 7, condition: 'shuffled', config: CONFIG, now, randomTail: 'abc123' });
  assert.deepEqual(Object.keys(doc), ['assignment_id', 'condition', 'file_prefix', 'start_time_iso', 'consent_given',
    'is_completed', 'config', 'trials']);
  assert.equal(doc.file_prefix, '2026-10-01_123456789Z_shuffled_a007_abc123');
  assert.equal(doc.start_time_iso, '2026-10-01T12:34:56.789Z');
  assert.deepEqual(doc.config, clone(CONFIG));
  assert.throws(() => buildInitialDocument({ assignmentId: 7, condition: '', config: CONFIG, now, randomTail: 'x' }), /condition is required/);
  assert.deepEqual(globalTrialProperties({ assignmentId: 7, condition: 'shuffled' }), { assignment_id: 7, condition: 'shuffled' });
  const session = await buildSession(row(7, 'shuffled'), CFG, tables);
  assert.deepEqual(Object.keys(planMetadata(session)),
    ['item_table_version', 'item_table_hash', 'schedule_sha256', 'balance_exactness', 'generation_stats']);
  assert.deepEqual([...TASK_PHASES], ['main']);
  // A question row: the record, the plugin's result, the scoring, the globals and the tidying.
  const response = {
    response: 'left', response_key: 'KeyF', rt: 1234, is_timed_out: false, trial_onset_time_ms: 10.5,
    continue_rt_ms: 300, copy_attempt_count: 0, blocked_shortcut_count: 0, invalid_key_count: 0,
    window_width_px: 1280, window_height_px: 800, device_pixel_ratio: 2, stage_scale: 1.1429,
  };
  const data = {
    ...session.main[0].record, ...response, trial_type: 'question-trial', trial_index: 12, time_elapsed: 9000,
    internal_node_id: '0.0-12.0', plugin_version: '1.0.0', ...globalTrialProperties({ assignmentId: 7, condition: 'shuffled' }),
  };
  Object.assign(data, scoreResponse(data));
  const events = [{ event: 'blur', time_ms: 5 }, { event: 'focus', time_ms: 6 }];
  assert.deepEqual(finalizeTrialRow(data, events, null), { browser_metadata: null });
  assert.equal(data.n_blur_events, 1);
  assert.equal(data.interaction_events_json, JSON.stringify(events));
  assert.ok(!('internal_node_id' in data) && !('plugin_version' in data));
  const rowKeys = [...RECORD_KEYS, ...Object.keys(response), 'trial_type', 'trial_index', 'time_elapsed',
    'assignment_id', 'condition', 'chosen_item', 'is_correct', 'is_knowledge_consistent',
    'interaction_events_json', 'n_blur_events'];
  assert.deepEqual(Object.keys(data).sort(), rowKeys.sort(), 'the fields of a saved question row');
  // A browser-check row: its browser fields go to the document root.
  const check = { trial_type: 'browser-check', phase: 'browser_check', browser: 'chrome', browser_version: '1', os: 'mac',
    mobile: false, width: 1280, height: 800, vsync_rate: 60 };
  const { browser_metadata: meta } = finalizeTrialRow(check, [], { width: 1440, height: 900, devicePixelRatio: 2 });
  assert.deepEqual(meta, { browser: 'chrome', browser_version: '1', os: 'mac', is_mobile: false, window_width_px: 1280,
    window_height_px: 800, screen_width_px: 1440, screen_height_px: 900, device_pixel_ratio: 2, vsync_rate_hz: 60 });
  assert.deepEqual(Object.keys(check).sort(), ['interaction_events_json', 'phase', 'trial_type']);
  // A survey row: the answers as JSON, without SurveyJS's progress entries.
  const survey = { trial_type: 'survey', response: { sp_notes: 'No', progress_1: 1 } };
  finalizeTrialRow(survey, [], null);
  assert.equal(survey.response_json, '{"sp_notes":"No"}');
  assert.ok(!('response' in survey));
});

// --- participant-facing text that depends on the configuration ------------------------

test('instructions: four pages built up one paragraph per screen; the example on I2 only', () => {
  const { pages } = instructions(CFG, tables);
  assert.deepEqual(pages.map((p) => p.id), ['I1', 'I2a', 'I2b', 'I2c', 'I6a', 'I6b', 'I6c', 'I8']);
  assert.deepEqual([...new Set(pages.map((p) => p.id.slice(0, 2)))], ['I1', 'I2', 'I6', 'I8']);
  assert.deepEqual(pages.filter((p) => p.title).map((p) => p.id), ['I1', 'I8']);
  assert.deepEqual(pages.map((p) => p.shownSteps), [1, 1, 2, 3, 1, 2, 3, 1]);
  assert.deepEqual(pages.filter((p) => p.example).map((p) => p.id), ['I2a', 'I2b', 'I2c']);
  // The example: the instruction domain's one-step question, its answer on the left (F).
  const ex = instructionExample(CFG, tables);
  const objects = new Map(slotTable(CFG.domains.instructions).flatMap((s) => s.items).map((it) => [it.item_id, it]));
  const label = (id) => `${objects.get(id).article} ${objects.get(id).name}`.trim();
  const [p, p1] = CFG.instructionExample.oneStepQuery;
  assert.equal(ex.leftLabel, label(CFG.instructionExample.itemIds[p1 - 1]));
  assert.equal(ex.rightLabel, label(CFG.instructionExample.itemIds[p - 1]));
  assert.equal(ex.statements.length, N - 1);
  assert.equal(ex.questionHtml, question(CFG, tables.domains.find((d) => d.domain_id === CFG.domains.instructions)));
});

test('main intro and breaks: the same bonus reminder', () => {
  const intro = mainIntro(CFG);
  assert.equal(intro.title, null);
  assert.ok(intro.paragraphs.includes(breakScreen(CFG).reminder));
});

// --- design constants the paper reports ------------------------------------------------

test('design constants: questions, animals, statements, blocks, breaks and timing', async () => {
  // 48 questions about nine animals, eight statements each, in four blocks of 12 (three breaks).
  assert.equal(CONFIG.mainQuestionCount, 48);
  assert.equal(CONFIG.slotCount, 9);
  assert.equal(CONFIG.breakEvery, 12);
  assert.equal(Math.floor((CONFIG.mainQuestionCount - 1) / CONFIG.breakEvery), 3, 'three breaks');
  assert.deepEqual(CONDITIONS, ['congruent', 'shuffled']);
  // 50 s to answer; Space accepted 0.8 s after the answer; a 0.5 s blank between questions; four
  // seconds of minimum viewing time on the instructions and the main intro.
  assert.equal(CONFIG.responseDeadlineMs, 50000);
  assert.equal(framesToMs(CONFIG.timing.confirmationMinFrames), 800);
  assert.equal(framesToMs(CONFIG.timing.itiFrames), 500);
  assert.equal(CONFIG.instructionMinViewMs, 4000);
  assert.equal(CONFIG.mainIntroMinViewMs, 4000);
  assert.ok(instructions(CFG, tables).pages.some((p) => p.steps.some((t) => t.includes('<strong>50 seconds</strong>'))));
  // Run caps: at most four questions in a row with the answer on one side, at most two with one
  // symbolic distance. Line order: at most two chain-adjacent statements on adjacent lines, at
  // most two consecutive lines in chain order, |rank correlation| below 0.5.
  assert.deepEqual(CONFIG.maxRun, { correctSide: 4, contextDistance: 2 });
  assert.equal(CONFIG.lineOrder.maxChainAdjacencies, 2);
  assert.equal(CONFIG.lineOrder.maxInOrderRun, 2);
  assert.equal(CONFIG.lineOrder.maxAbsTau, 0.5);
  // Shuffled orderings: 15-21 of the 36 pairs agree, three to five of the eight statements are
  // true, no more than two consecutive statements in one direction, 25-75% of the pairs agree
  // at every distance; |r(symbolic, real-world distance)| ≤ .10.
  assert.deepEqual(shuffleBounds(9, CONFIG.shuffle), {
    agreeLo: 15, agreeHi: 21, trueLo: 3, trueHi: 5, maxRun: 2, perDistance: [0.25, 0.75], distances: 6,
  });
  assert.equal(CONFIG.shuffle.maxAbsCorrDK, 0.10);
  // jsPsych 8.2.3.
  const page = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(page, /<script src="https:\/\/unpkg\.com\/jspsych@8\.2\.3"><\/script>/);
  // The consent form states the age range.
  assert.ok(consent(CFG).html.includes('between the ages of 18 and 65'));
});

test('design constants: 33 animals in nine weight classes of three to five, 0.47 log10 units apart', () => {
  const dom = tables.domains.find((d) => d.domain_id === CONFIG.domains.main);
  assert.equal(dom.norm_sources.length, 3, 'three databases');
  const classes = [...slotTable(CONFIG.domains.main)].sort((x, y) => x.slot - y.slot)
    .map((s) => s.items.filter((it) => it.eligible));
  assert.equal(classes.length, 9);
  assert.equal(classes.flat().length, 33);
  assert.ok(classes.every((c) => c.length >= 3 && c.length <= 5));
  const gaps = range(0, 7).map((k) => Math.min(...classes[k + 1].map((it) => it.magnitude))
    - Math.max(...classes[k].map((it) => it.magnitude)));
  assert.equal(Math.min(...gaps).toFixed(2), '0.47');
});

test('design constants: every session of both conditions has the properties the paper reports', async () => {
  for (const id of [0, 1, 2, 3, 55, 56, 101, 272]) {
    const condition = ASSIGNMENTS[id].condition;
    const s = await buildSession(ASSIGNMENTS[id], CFG, tables);
    const main = s.main.map((t) => t.record);
    const where = `assignment ${id} (${condition})`;
    for (const r of main) {
      // Two answers; nine animals, one from each weight class; eight statements, one per line.
      const ids = JSON.parse(r.context_ordering_json);
      assert.equal(ids.length, 9, where);
      assert.deepEqual([...JSON.parse(r.context_slots_json)].sort((a, b) => a - b), range(1, 9), where);
      assert.equal(JSON.parse(r.statements_text_json).length, 8, where);
      assert.equal(s.main[r.trial_number - 1].params.statements.length, 8, where);
      // The two end animals (context positions 1 and 9) and the lightest and heaviest weight
      // class are never queried.
      for (const c of [r.query_left_context_position, r.query_right_context_position]) assert.ok(c >= 2 && c <= 8, where);
      for (const x of [r.query_left_slot, r.query_right_slot]) assert.ok(x >= 2 && x <= 8, where);
      // Line order.
      assert.ok(r.line_order_chain_adjacencies <= 2 && r.line_order_max_in_order_run <= 2 && Math.abs(r.line_order_tau) < 0.5, where);
    }
    // Symbolic distances 1-6, eight questions each; each real-world distance on eight questions.
    for (const key of ['context_distance', 'knowledge_distance']) {
      assert.deepEqual([...countBy(main, (r) => r[key])].sort((a, b) => a[0] - b[0]), range(1, 6).map((d) => [d, 8]), `${where} ${key}`);
    }
    // Four blocks of 12; two questions per distance per block, one with the answer left and one
    // right.
    assert.deepEqual([...countBy(main, (r) => r.block_index)].sort(), [[1, 12], [2, 12], [3, 12], [4, 12]], where);
    for (let b = 1; b <= 4; b++) {
      for (let d = 1; d <= 6; d++) {
        const pair = main.filter((r) => r.block_index === b && r.context_distance === d);
        assert.deepEqual(pair.map((r) => r.correct_answer_context).sort(), ['left', 'right'], where);
        if (condition === 'shuffled') assert.deepEqual(pair.map((r) => r.query_congruence).sort(), ['agree', 'conflict'], where);
      }
    }
    // Blocks follow one another and the run caps hold over the whole session.
    assert.deepEqual(main.map((r) => r.block_index), [...main.map((r) => r.block_index)].sort((a, b) => a - b), where);
    for (const [key, max] of [['correct_answer_context', 4], ['context_distance', 2]]) {
      let run = 1;
      for (let i = 1; i < main.length; i++) {
        run = main[i][key] === main[i - 1][key] ? run + 1 : 1;
        assert.ok(run <= max, `${where} ${key}`);
      }
    }
    // No pair of animals is queried twice; each animal appears equally often within one.
    assert.equal(new Set(main.map((r) => r.item_pair_key)).size, 48, where);
    assert.ok(['exact', 'pm1'].includes(s.balance_exactness.items_by_slot), where);
    if (condition === 'congruent') {
      // Every statement and every answer agree with the real-world order.
      assert.ok(main.every((r) => r.ordering_true_statements === 8 && r.knowledge_answer === r.correct_answer_context), where);
    } else {
      // Exactly half of the questions agree with the real-world order at every symbolic and every
      // real-world distance, and the two distances are nearly uncorrelated.
      for (const key of ['context_distance', 'knowledge_distance']) {
        for (let d = 1; d <= 6; d++) {
          const at = main.filter((r) => r[key] === d);
          assert.equal(at.filter((r) => r.knowledge_answer === r.correct_answer_context).length * 2, at.length, `${where} ${key}=${d}`);
        }
      }
      const xs = main.map((r) => r.context_distance); const ys = main.map((r) => r.knowledge_distance);
      const mean = (v) => v.reduce((a, b) => a + b, 0) / v.length;
      const mx = mean(xs); const my = mean(ys);
      const cov = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0);
      const r = cov / Math.sqrt(xs.reduce((a, x) => a + (x - mx) ** 2, 0) * ys.reduce((a, y) => a + (y - my) ** 2, 0));
      assert.ok(Math.abs(r) <= 0.10 + 1e-9, `${where}: r = ${r}`);
      // Every ordering is balanced.
      assert.ok(main.every((r) => isBalancedOrdering(JSON.parse(r.context_slots_json), CFG)), where);
    }
  }
});
