/**
 * The experiment's configuration, and `validateConfig`, which checks it against the item tables
 * at start-up.
 *
 * A plain object: no URL parsing, no DOM, no jsPsych, so Node can import it (the tests and
 * replay.mjs). The times in `timing` are frame counts at `timing.refreshRate` (60 Hz);
 * `framesToMs` converts them.
 *
 * Coordinates (js/trial-logic.js): world slot s = 1..N orders the items by real-world magnitude;
 * context position c = 1..N orders them as the statements of a question do.
 *
 * `validateConfig` checks the instruction example with the line-order rule of js/trial-logic.js,
 * which in turn imports `framesToMs` and `CONDITIONS` from here. The cycle is safe: neither
 * module uses the other's exports while it is being evaluated, only inside functions.
 *
 * @module config
 */

import { isAcceptedLineOrder, mirrorTertilePicks } from './trial-logic.js';

/** The between-subjects conditions (the assignment table's `condition`). */
export const CONDITIONS = ['congruent', 'shuffled'];

export const CONFIG = {

  // -- Structure --
  slotCount: 9,                  // N: items per question, one from each world slot.
  // A multiple of 2 × (N − 3) = 12, so that every block of 12 holds two questions per symbolic
  // distance.
  mainQuestionCount: 48,
  breakEvery: 12,                // A break after every breakEvery main questions.

  // -- Domains --
  // `main`: the main questions; `instructions`: the instruction example. Both need N-slot
  // tables, and no item ID may be in both.
  domains: { main: 'animal_weight', instructions: 'object_size' },
  // Must equal data/item_tables.json's `table_version`.
  itemTableVersion: '2026-09-30.1',

  // -- Instruction example (instructions domain) --
  // The example question below the text of the instruction pages I2a-c. `itemIds` are listed by
  // context position 1..N, i.e. in the statements' order (statement k, 0-based, reads
  // "itemIds[k + 1] is bigger than itemIds[k]"), and are in world order, so every statement is
  // true. `lineOrder` gives the statement indices (0-based) in screen order. `oneStepQuery`
  // [p, p + 1] is a pair of interior context positions (2..N - 1) linked by statement p - 1
  // (0-based); the statements' answer is the item at p + 1.
  instructionExample: {
    itemIds: ['coin', 'egg', 'mug', 'toaster', 'guitar', 'piano', 'car', 'bus', 'cruise_ship'],
    lineOrder: [5, 1, 4, 7, 2, 6, 0, 3],
    oneStepQuery: [7, 8],
  },

  // -- Balanced orderings: the orderings of the shuffled condition --
  shuffle: {
    agreePairsFractionRange: [15 / 36, 21 / 36],  // Inclusive; of C(N, 2) pairs, rounded inward.
    trueStatementsMaxDeviation: 1,                // |true statements − (N − 1)/2| ≤ 1.
    maxSameDirectionRun: 2,
    perDistanceAgreeRange: [0.25, 0.75],          // Inclusive, at d = 1..N − 3.
    maxAbsCorrDK: 0.10,                           // |r(symbolic, real-world distance)|, shuffled.
    maxDraws: 100000,
  },

  // -- Line order --
  lineOrder: {
    maxChainAdjacencies: 2,
    maxInOrderRun: 2,            // Ascending or descending.
    maxAbsTau: 0.5,              // Strict: |τ| < 0.5.
    maxDraws: 10000,
  },

  // -- Run caps and sequencing (within blocks, checked across block boundaries) --
  maxRun: {
    correctSide: 4,
    contextDistance: 2,
  },
  sequenceMaxAttempts: 100000,
  sequenceMaxReseeds: 20,

  // -- Timing --
  responseDeadlineMs: 50000,
  timing: {
    confirmationMinFrames: 48,       // ≈ 800 ms before "Press space to continue." appears
    itiFrames: 30,                   // ≈ 500 ms blank between questions
    continueLockoutFrames: 24,       // ≈ 400 ms before Space ends a continue screen
    refreshRate: 60,
  },
  instructionMinViewMs: 4000,
  mainIntroMinViewMs: 4000,
  fontLoadTimeoutMs: 3000,

  // -- Display (px at stage scale 1, a 1024 × 700 window) --
  display: {
    statementFontPx: 22,
    statementPitchPx: 36,
    queryFontPx: 24,
    statementsColumnWidthPx: 600,
  },

  // -- Browser check --
  browser: {
    minWidth: 1024,
    minHeight: 700,
  },
};

/**
 * Convert a frame count to milliseconds at the configured refresh rate.
 * @param {number} frames
 * @param {object} [cfg=CONFIG]
 * @returns {number}
 */
export function framesToMs(frames, cfg = CONFIG) {
  return Math.round((frames / cfg.timing.refreshRate) * 1000);
}

// --- validateConfig ---

const EPS = 1e-9;

function slotTableFor(domain, slotCount) {
  const tables = domain && domain.slot_tables;
  return tables ? tables[String(slotCount)] : undefined;
}

/** item_id → {item, slot} of the eligible items of a domain's N-slot table (null if unusable). */
function eligibleIndex(domain, slotCount) {
  const slots = slotTableFor(domain, slotCount);
  if (!Array.isArray(slots) || slots.some((s) => typeof s !== 'object')) return null;
  const out = new Map();
  for (const s of slots) for (const it of s.items || []) if (it.eligible === true) out.set(it.item_id, { item: it, slot: s.slot });
  return out;
}

/**
 * How many questions the mirror/tertile skeleton sends to each pair of world slots (x, x + kd)
 * at this question count: the picks at distance kd give x. The picks are deterministic whenever
 * m is even; otherwise a single pick from a two-member central group is random, so both choices
 * are counted (the capacity check then uses the worst case).
 * @param {object} cfg
 * @returns {Map<string, number>} "x-y" → questions (maximum over the random picks).
 */
export function worldSlotPairDemand(cfg) {
  const N = cfg.slotCount;
  const D = N - 3;
  const m = cfg.mainQuestionCount / D;
  const demand = new Map();
  if (!Number.isInteger(m) || m < 1) return demand;
  for (const rng of [() => 0, () => 1 - 1e-12]) {
    const once = new Map();
    for (let kd = 1; kd <= D; kd++) {
      for (const p of mirrorTertilePicks(rng, N, kd, m)) {
        const key = `${p.a}-${p.a + kd}`;
        once.set(key, (once.get(key) || 0) + 1);
      }
    }
    for (const [k, n] of once) demand.set(k, Math.max(demand.get(k) || 0, n));
  }
  return demand;
}

/**
 * Validate the configuration against the loaded item tables. Runs at start-up and in the tests.
 * Collects every failure and throws one Error listing them all; each message starts with its
 * rule's id.
 *
 *  1  slotCount is 9.
 *  2  mainQuestionCount is a positive multiple of 2 × (N − 3) and at most 2 × (N − 3)² (the
 *     Latin incidence takes each column at most twice).
 *  3  Capacity: every pair of world slots the skeleton queries has at least as many distinct
 *     main-domain item pairs as questions (no query pair is asked twice); computed from the
 *     tables.
 *  4  domains.main and domains.instructions differ and each has an N-slot table holding slots
 *     1..N once, every slot with an eligible item.
 *  5  No item ID is in both domains.
 *  6  Every forbidden pair whose items are both eligible sits within one slot (so it can never
 *     appear in one question).
 *  7  itemTableVersion matches the table file.
 *  8  instructionExample (see `instructionExampleProblems`).
 *  9  Threshold ranges are ordered.
 * 10  Timing values are positive; the confirmation time is shorter than the deadline.
 * 11  breakEvery is a positive integer below mainQuestionCount; the run caps are positive
 *     integers.
 *
 * @param {object} cfg - The CONFIG object (or a modified copy).
 * @param {object} tables - Parsed data/item_tables.json.
 * @returns {true} When every rule holds.
 * @throws {Error} Listing every failed rule.
 */
export function validateConfig(cfg, tables) {
  const errors = [];
  const fail = (id, msg) => errors.push(`[${id}] ${msg}`);
  const N = cfg.slotCount;
  const D = N - 3;
  const Q = cfg.mainQuestionCount;
  const domainsById = new Map(((tables && tables.domains) || []).map((d) => [d.domain_id, d]));
  const doms = cfg.domains || {};

  // 1
  if (N !== 9) fail(1, `slotCount must be 9 (got ${N}).`);
  // 2
  const qOk = Number.isInteger(Q) && Q > 0 && Q % (2 * D) === 0 && Q <= 2 * D * D;
  if (!qOk) {
    fail(2, `mainQuestionCount must be a positive multiple of 2 × (slotCount − 3) = ${2 * D}, at most ${2 * D * D} (got ${Q}).`);
  }
  // 4
  const idx = {};
  for (const role of ['main', 'instructions']) {
    const id = doms[role];
    const dom = domainsById.get(id);
    const slots = slotTableFor(dom, N);
    if (typeof id !== 'string' || !dom) { fail(4, `domains.${role} '${id}' is missing from the item tables.`); continue; }
    if (!Array.isArray(slots) || slots.length !== N || slots.some((s) => typeof s !== 'object')) {
      fail(4, `domains.${role} '${id}' has no ${N}-slot table.`);
      continue;
    }
    const slotNumbers = slots.map((s) => s.slot).sort((x, y) => x - y);
    if (slotNumbers.some((v, i) => v !== i + 1)) fail(4, `domain '${id}': the ${N}-slot table must hold slots 1..${N} once each (got ${slotNumbers.join(', ')}).`);
    slots.forEach((s) => {
      if (!(s.items || []).some((it) => it.eligible === true)) fail(4, `domain '${id}' slot ${s.slot} has no eligible item.`);
    });
    idx[role] = eligibleIndex(dom, N);
  }
  if (doms.main === doms.instructions) fail(4, `domains.main and domains.instructions must differ (both '${doms.main}').`);
  // 3
  if (qOk && idx.main) {
    const perSlot = new Map();
    for (const { slot } of idx.main.values()) perSlot.set(slot, (perSlot.get(slot) || 0) + 1);
    const short = [];
    for (const [key, need] of worldSlotPairDemand(cfg)) {
      const [x, y] = key.split('-').map(Number);
      const have = (perSlot.get(x) || 0) * (perSlot.get(y) || 0);
      if (need > have) short.push(`(${x}, ${y}) needs ${need} but has ${perSlot.get(x) || 0} × ${perSlot.get(y) || 0} = ${have}`);
    }
    if (short.length) {
      let best = 0;
      for (let q = 2 * D; q <= 2 * D * D; q += 2 * D) {
        const probe = { ...cfg, mainQuestionCount: q };
        const ok = [...worldSlotPairDemand(probe)].every(([key, need]) => {
          const [x, y] = key.split('-').map(Number);
          return need <= (perSlot.get(x) || 0) * (perSlot.get(y) || 0);
        });
        if (!ok) break;
        best = q;
      }
      fail(3, `mainQuestionCount ${Q} asks some pair of world slots more often than '${doms.main}' has distinct item pairs, `
        + `and no query pair may be asked twice: ${short.join('; ')}. The largest feasible count with these tables is ${best}.`);
    }
  }
  // 5
  if (idx.main && idx.instructions) {
    const tableIds = (role) => {
      const out = new Set();
      for (const s of slotTableFor(domainsById.get(doms[role]), N)) for (const it of s.items || []) out.add(it.item_id);
      return out;
    };
    const mainIds = tableIds('main');
    const shared = [...tableIds('instructions')].filter((id) => mainIds.has(id));
    if (shared.length) fail(5, `item IDs in both '${doms.main}' and '${doms.instructions}': ${shared.join(', ')}.`);
  }
  // 6
  for (const role of ['main', 'instructions']) {
    if (!idx[role]) continue;
    for (const pair of domainsById.get(doms[role]).forbidden_adjacent_pairs || []) {
      const [p, q] = pair.map((id) => idx[role].get(id));
      if (p && q && p.slot !== q.slot) {
        fail(6, `domain '${doms[role]}': forbidden pair ${pair.join('/')} spans slots ${p.slot} and ${q.slot}; both are eligible, so they could appear in one question.`);
      }
    }
  }
  // 7
  if (!tables || cfg.itemTableVersion !== tables.table_version) {
    fail(7, `itemTableVersion '${cfg.itemTableVersion}' does not match the table file's table_version '${tables && tables.table_version}'.`);
  }
  // 8
  if (idx.instructions) for (const msg of instructionExampleProblems(cfg, idx.instructions)) fail(8, msg);
  // 9
  const orderedRange = (r) => Array.isArray(r) && r.length === 2 && r[0] <= r[1] && r[0] >= 0 && r[1] <= 1;
  if (!orderedRange(cfg.shuffle.agreePairsFractionRange)) fail(9, 'shuffle.agreePairsFractionRange must be an ordered range within [0, 1].');
  if (!orderedRange(cfg.shuffle.perDistanceAgreeRange)) fail(9, 'shuffle.perDistanceAgreeRange must be an ordered range within [0, 1].');
  if (orderedRange(cfg.shuffle.agreePairsFractionRange)) {
    const P = (N * (N - 1)) / 2;
    const lo = Math.ceil(cfg.shuffle.agreePairsFractionRange[0] * P - EPS);
    const hi = Math.floor(cfg.shuffle.agreePairsFractionRange[1] * P + EPS);
    if (lo > hi) fail(9, `shuffle.agreePairsFractionRange rounds inward to an empty count range [${lo}, ${hi}].`);
  }
  if (!(cfg.shuffle.trueStatementsMaxDeviation >= 0)) fail(9, 'shuffle.trueStatementsMaxDeviation must be ≥ 0.');
  if (!(cfg.shuffle.maxAbsCorrDK >= 0)) fail(9, 'shuffle.maxAbsCorrDK must be ≥ 0.');
  // 10
  const positive = {
    responseDeadlineMs: cfg.responseDeadlineMs,
    'timing.confirmationMinFrames': cfg.timing.confirmationMinFrames,
    'timing.itiFrames': cfg.timing.itiFrames,
    'timing.continueLockoutFrames': cfg.timing.continueLockoutFrames,
    'timing.refreshRate': cfg.timing.refreshRate,
    instructionMinViewMs: cfg.instructionMinViewMs,
    mainIntroMinViewMs: cfg.mainIntroMinViewMs,
    fontLoadTimeoutMs: cfg.fontLoadTimeoutMs,
  };
  for (const [k, v] of Object.entries(positive)) {
    if (!(typeof v === 'number' && v > 0)) fail(10, `${k} must be a positive number (got ${v}).`);
  }
  const confirmMs = framesToMs(cfg.timing.confirmationMinFrames, cfg);
  if (!(confirmMs < cfg.responseDeadlineMs)) fail(10, `confirmation time (${confirmMs} ms) must be shorter than responseDeadlineMs.`);
  // 11
  if (!(Number.isInteger(cfg.breakEvery) && cfg.breakEvery > 0 && cfg.breakEvery < Q)) {
    fail(11, `breakEvery must be a positive integer below the ${Q} main questions (got ${cfg.breakEvery}).`);
  }
  for (const k of ['correctSide', 'contextDistance']) {
    if (!(Number.isInteger(cfg.maxRun && cfg.maxRun[k]) && cfg.maxRun[k] >= 1)) fail(11, `maxRun.${k} must be a positive integer (got ${cfg.maxRun && cfg.maxRun[k]}).`);
  }

  if (errors.length) {
    throw new Error(`[validateConfig] ${errors.length} problem(s):\n  ${errors.join('\n  ')}`);
  }
  return true;
}


/**
 * Problems with `instructionExample` against the instructions domain's eligible items (rule 8
 * of validateConfig). Empty when every rule holds: N distinct eligible items, one per world slot,
 * in world order; a `lineOrder` that orders the N - 1 statement indices (0-based) and that the
 * line-order rule accepts; a `oneStepQuery` [p, p + 1] of interior positions (2..N - 1).
 * @param {object} cfg
 * @param {Map<string, {item: object, slot: number}>} eligible - item_id → entry.
 * @returns {string[]}
 */
function instructionExampleProblems(cfg, eligible) {
  const N = cfg.slotCount;
  const ex = cfg.instructionExample;
  const where = 'instructionExample';
  if (!ex || !Array.isArray(ex.itemIds) || ex.itemIds.length !== N) return [`${where}.itemIds must list ${N} item IDs.`];
  const unknown = ex.itemIds.filter((id) => !eligible.has(id));
  if (unknown.length) return [`${where}.itemIds holds items that are not eligible in '${cfg.domains.instructions}': ${unknown.join(', ')}.`];
  const out = [];
  const o = ex.itemIds.map((id) => eligible.get(id).slot);
  if (o.some((s, i) => s !== i + 1)) out.push(`${where} must be the world order (slots ${o.join(', ')}).`);
  const lo = ex.lineOrder;
  const loOk = Array.isArray(lo) && lo.length === N - 1 && [...lo].sort((x, y) => x - y).every((v, i) => v === i);
  if (!loOk) out.push(`${where}.lineOrder must order the statement indices 0..${N - 2}.`);
  else if (!isAcceptedLineOrder(lo.map((k) => k + 1), cfg)) out.push(`${where}.lineOrder ${JSON.stringify(lo)} breaks the line-order rule.`);
  const q = ex.oneStepQuery;
  const qOk = Array.isArray(q) && q.length === 2 && Number.isInteger(q[0]) && q[1] === q[0] + 1 && q[0] >= 2 && q[1] <= N - 1;
  if (!qOk) out.push(`${where}.oneStepQuery must be [p, p + 1] with 2 ≤ p and p + 1 ≤ ${N - 1}.`);
  return out;
}
