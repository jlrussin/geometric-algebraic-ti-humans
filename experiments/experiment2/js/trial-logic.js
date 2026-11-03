/**
 * The questions of a session, generated from its assignment row (between-subjects design: each
 * participant does the congruent or the shuffled condition). Pure: no jsPsych, no DOM.
 *
 * No Math.random. Every random draw comes from a stream of one stage, made by
 * `makeStream(assignmentId, label)` (js/seeded-rng.js), so the same assignment row always yields
 * the same questions, and changing one stage never changes another stage's draws. The stages, in
 * call order: skeleton, knowledge (shuffled only), blocks, sides, orderings (shuffled only),
 * lines, items (items:retry<n> on a reseed), sequence (sequence:retry<n>).
 *
 * Coordinates. World slot s ∈ 1..N ascends in real-world magnitude. Context position
 * c ∈ 1..N ascends according to the statements. An ordering is an array `o` with o[c − 1] =
 * the world slot of the item at context position c. Statement c (1..N−1) reads "item at c+1
 * <relation> item at c". A query uses context positions (a, a + d), 2 ≤ a, a + d ≤ N − 1 (the
 * end items are never queried); the statements' answer is the item at a + d. The symbolic
 * distance d is saved as `context_distance`; the real-world distance kd, the distance between
 * the two queried items' world slots, as `knowledge_distance`.
 *
 * Main entry point: `buildSession(assignment, cfg, tables)`.
 *
 * @module trial-logic
 */

import { makeStream } from './seeded-rng.js';
import { framesToMs, CONDITIONS } from './config.js';
import { question as questionCopy } from './copy.js';

const EPS = 1e-9;

// --- Primitives -------------------------------------------------------------

/** Integer in [0, n): Math.floor(rng() * n). */
function randInt(rng, n) {
  return Math.floor(rng() * n);
}

/** Fisher–Yates, i from n − 1 down to 1, j = floor(rng() · (i + 1)). In place. */
function shuffleInPlace(rng, arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

/**
 * Fisher–Yates on a copy: the shuffle every stage uses.
 * @template T
 * @param {function(): number} rng
 * @param {T[]} arr
 * @returns {T[]}
 */
export function shuffled(rng, arr) {
  return shuffleInPlace(rng, arr.slice());
}

/** Inclusive integer range [lo, hi]. */
function range(lo, hi) {
  const out = [];
  for (let i = lo; i <= hi; i++) out.push(i);
  return out;
}

/** Pearson correlation of two equal-length number arrays (NaN if a variance is 0). */
function pearson(xs, ys) {
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0; let sxx = 0; let syy = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx; const dy = ys[i] - my;
    sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
  }
  return sxy / Math.sqrt(sxx * syy);
}

function pairKey(idA, idB) {
  return idA < idB ? `${idA}|${idB}` : `${idB}|${idA}`;
}

// --- Skeleton: the mirror/tertile rule ----------------------------------------

/**
 * Mirror/tertile picks at one distance, in generation order. The allowed a are 2..N−1−δ;
 * the mirror of a is N + 1 − a − δ. Mirror groups are ordered from outer to central; passes
 * over the groups take a whole group while `remaining` covers it, and otherwise one member of
 * the most central group, uniformly at random. A whole group of two is emitted low then high.
 * @param {function(): number} rng
 * @param {number} slotCount - N.
 * @param {number} d - The distance δ (symbolic distance or real-world distance).
 * @param {number} m - Picks wanted.
 * @returns {Array<{a: number, bin: ('low'|'center'|'high')}>}
 */
export function mirrorTertilePicks(rng, slotCount, d, m) {
  const groups = [];
  const seen = new Set();
  for (let a = 2; a <= slotCount - 1 - d; a++) {        // ascending a = outer → central
    if (seen.has(a)) continue;
    const mirror = slotCount + 1 - a - d;
    const g = mirror === a ? [a] : [Math.min(a, mirror), Math.max(a, mirror)];
    g.forEach((x) => seen.add(x));
    groups.push(g);
  }
  const central = groups[groups.length - 1];
  const picks = [];
  let remaining = m;
  while (remaining > 0) {
    for (const g of groups) {
      if (remaining === 0) break;
      if (remaining >= g.length) {
        if (g.length === 1) picks.push({ a: g[0], bin: 'center' });
        else picks.push({ a: g[0], bin: 'low' }, { a: g[1], bin: 'high' });
        remaining -= g.length;
      } else {
        picks.push({ a: central[randInt(rng, central.length)], bin: 'center' });
        remaining -= 1;
      }
    }
  }
  return picks;
}

/**
 * The shared skeleton (stream `skeleton`): m = mainQuestionCount / (N − 3) mirror/tertile picks
 * at every distance δ = 1..N−3. Picks at symbolic distance d give the queried context positions
 * (a, a + d); picks at real-world distance kd give the queried world slots (x, x + kd). The rule
 * draws one number per single pick, but at N = 9 with m even (validateConfig rule 2) every single
 * pick comes from a one-member central group, so the picks are forced and both conditions share
 * one deterministic skeleton.
 * @param {function(): number} rng - Stream `skeleton`.
 * @param {object} cfg
 * @returns {{m: number, picks: Array<Array<{a: number, bin: string}>>}} picks[δ − 1].
 */
export function sampleSkeleton(rng, cfg) {
  const N = cfg.slotCount;
  const D = N - 3;
  const m = cfg.mainQuestionCount / D;
  if (!Number.isInteger(m) || m < 1) {
    throw new Error(`[sampleSkeleton] mainQuestionCount (${cfg.mainQuestionCount}) must be a positive multiple of N − 3 (${D}).`);
  }
  return { m, picks: range(1, D).map((d) => mirrorTertilePicks(rng, N, d, m)) };
}

/**
 * Mirror units of one distance's picks: index pairs [i, j] whose members
 * must go one to agree and one to conflict questions. A whole mirror group
 * (low, high) is one unit; center picks pair up in generation order (they
 * share a position or sit in the central group).
 */
function mirrorUnits(picks) {
  const units = [];
  const centers = [];
  for (let i = 0; i < picks.length; i++) {
    if (picks[i].bin === 'low') { units.push([i, i + 1]); i++; } else centers.push(i);
  }
  if (centers.length % 2) throw new Error('[mirrorUnits] an odd number of center picks cannot be split in half.');
  for (let k = 0; k < centers.length; k += 2) units.push([centers[k], centers[k + 1]]);
  return units;
}

/**
 * Congruent questions: identity ordering, so each pick at distance d queries
 * context positions and world slots (a, a + d), and kd = d. Canonical order:
 * d, then pick order.
 * @param {ReturnType<typeof sampleSkeleton>} skeleton
 * @returns {Array<{d: number, kd: number, congruence: string, a: number, aBin: string, x: number,
 *   xBin: string}>}
 */
function congruentQuestions(skeleton) {
  const out = [];
  skeleton.picks.forEach((picks, i) => {
    for (const p of picks) out.push({ d: i + 1, kd: i + 1, congruence: 'agree', a: p.a, aBin: p.bin, x: p.a, xBin: p.bin });
  });
  return out;
}

// --- Real-world distances (shuffled condition) -------------------------------

/**
 * The shuffled condition's questions (stream `knowledge`).
 *
 * 1. Latin incidence. A D × D Latin square L (rows kd, symbols d: the cyclic
 *    square with rows, columns and symbols randomly reordered) and m columns:
 *    min(m, D) distinct base columns, plus m − D distinct extra columns when
 *    m > D. Each column holds every d and every kd once, so each d and each
 *    kd gets exactly m questions. Base columns: the first half agree, the
 *    second half conflict; extra columns alternate agree, conflict. So every
 *    d and every kd has m/2 agree and m/2 conflict questions.
 * 2. Resample (1) until |r(d, kd)| ≤ shuffle.maxAbsCorrDK over the m·D
 *    questions (r = 0 whenever the columns are exactly the D base columns).
 * 3. Mirror split of the context positions: for d = 1..D, each mirror unit
 *    of the skeleton's picks at d sends one member to agree and one to
 *    conflict (a coin per unit, in unit order); within (d, label) the
 *    positions are shuffled onto the questions in canonical order.
 * 4. The same for the world-slot pairs: picks at kd = 1..D give x.
 *
 * Canonical order: d, then column order. Agree questions put world slot x at
 * position a and x + kd at a + d; conflict questions the reverse.
 * @param {function(): number} rng - Stream `knowledge`.
 * @param {ReturnType<typeof sampleSkeleton>} skeleton
 * @param {object} cfg
 * @returns {{questions: Array<{d: number, kd: number, congruence: string, a: number, aBin: string,
 *   x: number, xBin: string}>, latin_square: number[][], columns: number[], labels: string[],
 *   draws: number, r_dk: number}}
 */
export function assignKnowledgeDistances(rng, skeleton, cfg) {
  const D = cfg.slotCount - 3;
  const { m } = skeleton;
  if (m % 2 || m > 2 * D || D % 2) {
    throw new Error(`[assignKnowledgeDistances] needs an even m ≤ 2D and an even D (m = ${m}, D = ${D}).`);
  }
  let draws = 0;
  let L; let columns; let labels; let entries; let r;
  for (;;) {
    draws++;
    if (draws > cfg.shuffle.maxDraws) {
      throw new Error(`[assignKnowledgeDistances] no Latin incidence met |r(d, kd)| ≤ ${cfg.shuffle.maxAbsCorrDK} within ${cfg.shuffle.maxDraws} draws.`);
    }
    const rowPerm = shuffled(rng, range(0, D - 1));
    const colPerm = shuffled(rng, range(0, D - 1));
    const symbols = shuffled(rng, range(1, D));
    L = rowPerm.map((ri) => colPerm.map((ci) => symbols[(ri + ci) % D]));
    const base = shuffled(rng, range(0, D - 1)).slice(0, Math.min(m, D));
    const extras = m > D ? shuffled(rng, range(0, D - 1)).slice(0, m - D) : [];
    columns = [...base, ...extras];
    labels = [
      ...base.map((_, j) => (j < base.length / 2 ? 'agree' : 'conflict')),
      ...extras.map((_, j) => (j % 2 === 0 ? 'agree' : 'conflict')),
    ];
    entries = [];
    columns.forEach((c, j) => { for (let kd = 1; kd <= D; kd++) entries.push({ d: L[kd - 1][c], kd, congruence: labels[j], col: j }); });
    r = pearson(entries.map((x) => x.d), entries.map((x) => x.kd));
    if (Math.abs(r) <= cfg.shuffle.maxAbsCorrDK + EPS) break;
  }
  entries.sort((p, q) => p.d - q.d || p.col - q.col);
  const questions = entries.map((c) => ({ d: c.d, kd: c.kd, congruence: c.congruence, a: null, aBin: null, x: null, xBin: null }));
  const split = (key, set) => {
    for (let delta = 1; delta <= D; delta++) {
      const picks = skeleton.picks[delta - 1];
      const byLabel = { agree: [], conflict: [] };
      for (const [i, j] of mirrorUnits(picks)) {
        const first = randInt(rng, 2) === 0;
        byLabel.agree.push(picks[first ? i : j]);
        byLabel.conflict.push(picks[first ? j : i]);
      }
      for (const label of ['agree', 'conflict']) {
        const targets = questions.filter((q) => q[key] === delta && q.congruence === label);
        shuffled(rng, byLabel[label]).forEach((p, k) => set(targets[k], p));
      }
    }
  };
  split('d', (q, p) => { q.a = p.a; q.aBin = p.bin; });
  split('kd', (q, p) => { q.x = p.a; q.xBin = p.bin; });
  return { questions, latin_square: L, columns, labels, draws, r_dk: r };
}

// --- Blocks and sides -------------------------------------------------------

/**
 * Blocks (stream `blocks`): B = mainQuestionCount / (2D) blocks, each with
 * two questions per symbolic distance; in the shuffled condition one agree and
 * one conflict. For d = 1..D and each label present (agree, then conflict),
 * the questions (canonical order) are shuffled and dealt to blocks 1..B in
 * equal runs.
 * @param {function(): number} rng - Stream `blocks`.
 * @param {Array<{d: number, congruence: string}>} questions
 * @param {object} cfg
 * @returns {number[]} block[j] ∈ 1..B (1-based), aligned with questions.
 */
export function assignBlocks(rng, questions, cfg) {
  const D = cfg.slotCount - 3;
  const B = questions.length / (2 * D);
  const block = new Array(questions.length).fill(null);
  for (let d = 1; d <= D; d++) {
    for (const label of ['agree', 'conflict']) {
      const idx = questions.map((q, j) => j).filter((j) => questions[j].d === d && questions[j].congruence === label);
      if (!idx.length) continue;
      const per = idx.length / B;
      if (!Number.isInteger(per)) throw new Error(`[assignBlocks] d = ${d} ${label}: ${idx.length} questions do not split over ${B} blocks.`);
      shuffled(rng, idx).forEach((j, k) => { block[j] = Math.floor(k / per) + 1; });
    }
  }
  return block;
}

/**
 * Correct-answer sides (stream `sides`), after the blocks. Every (block, d) pair of questions has
 * one correct-left and one correct-right question.
 * - Congruent: per block 1..B and d = 1..D, a coin decides whether the pair's first question
 *   (canonical order) is the left one.
 * - Shuffled (one agree and one conflict question per pair): a B × D matrix says in which pairs
 *   the agree question is left. Each row is a random D/2-subset of the distances (the first D/2
 *   of a shuffle of 1..D); the matrix is resampled until every column holds ⌊B/2⌋ or ⌈B/2⌉
 *   agree-left entries. So every block has D/2 agree-left and D/2 conflict-left questions, and
 *   at every d the agree (and the conflict) questions are left in half the blocks (±1 when B is
 *   odd).
 * @param {function(): number} rng - Stream `sides`.
 * @param {Array<{d: number, congruence: string}>} questions
 * @param {number[]} block - From assignBlocks.
 * @param {object} cfg
 * @returns {{sides: string[], draws: number}} sides[j] ∈ {'left', 'right'}; draws = matrix
 *   attempts (1 for congruent).
 */
export function assignSides(rng, questions, block, cfg) {
  const D = cfg.slotCount - 3;
  const B = questions.length / (2 * D);
  const sides = new Array(questions.length).fill(null);
  const pairAt = (b, d) => questions.map((q, j) => j).filter((j) => block[j] === b && questions[j].d === d);
  const hasConflict = questions.some((q) => q.congruence === 'conflict');
  if (!hasConflict) {
    for (let b = 1; b <= B; b++) {
      for (let d = 1; d <= D; d++) {
        const [j0, j1] = pairAt(b, d);
        const firstLeft = randInt(rng, 2) === 0;
        sides[j0] = firstLeft ? 'left' : 'right';
        sides[j1] = firstLeft ? 'right' : 'left';
      }
    }
    return { sides, draws: 1 };
  }
  const lo = Math.floor(B / 2); const hi = Math.ceil(B / 2);
  let rows; let draws = 0;
  for (;;) {
    draws++;
    if (draws > cfg.sequenceMaxAttempts) throw new Error(`[assignSides] no balanced side matrix within ${cfg.sequenceMaxAttempts} draws.`);
    rows = range(1, B).map(() => new Set(shuffled(rng, range(1, D)).slice(0, D / 2)));
    const ok = range(1, D).every((d) => {
      const n = rows.filter((row) => row.has(d)).length;
      return n === lo || n === hi;
    });
    if (ok) break;
  }
  questions.forEach((q, j) => {
    const agreeLeft = rows[block[j] - 1].has(q.d);
    sides[j] = (q.congruence === 'agree') === agreeLeft ? 'left' : 'right';
  });
  return { sides, draws };
}

// --- Balanced orderings (shuffled condition) ---------------------------------

/**
 * The bounds of a balanced ordering at slotCount N, as inclusive integer counts: agreeing pairs
 * (fraction range of C(N,2), rounded inward) and true statements ((N − 1)/2 ±
 * trueStatementsMaxDeviation, rounded inward).
 * @param {number} slotCount
 * @param {object} shuffleCfg - cfg.shuffle.
 * @returns {{agreeLo: number, agreeHi: number, trueLo: number, trueHi: number,
 *   maxRun: number, perDistance: number[], distances: number}}
 */
export function shuffleBounds(slotCount, shuffleCfg) {
  const P = (slotCount * (slotCount - 1)) / 2;
  const mid = (slotCount - 1) / 2;
  return {
    agreeLo: Math.ceil(shuffleCfg.agreePairsFractionRange[0] * P - EPS),
    agreeHi: Math.floor(shuffleCfg.agreePairsFractionRange[1] * P + EPS),
    trueLo: Math.ceil(mid - shuffleCfg.trueStatementsMaxDeviation - EPS),
    trueHi: Math.floor(mid + shuffleCfg.trueStatementsMaxDeviation + EPS),
    maxRun: shuffleCfg.maxSameDirectionRun,
    perDistance: shuffleCfg.perDistanceAgreeRange.slice(),
    distances: slotCount - 3,
  };
}

/**
 * Agreement statistics of an ordering.
 * @param {number[]} o - o[c − 1] = world slot at context position c.
 * @returns {{agree_pairs: number, true_statements: number, max_run: number,
 *   agree_by_distance: number[]}} agree_by_distance[d − 1] = agreeing pairs
 *   (i, i + d) for d = 1..N−1.
 */
export function orderingStats(o) {
  const n = o.length;
  const byD = new Array(n - 1).fill(0);
  let agree = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (o[i] < o[j]) { agree++; byD[j - i - 1]++; }
    }
  }
  let maxRun = 1; let run = 1;
  for (let c = 1; c < n - 1; c++) {
    const same = (o[c] < o[c + 1]) === (o[c - 1] < o[c]);
    run = same ? run + 1 : 1;
    if (run > maxRun) maxRun = run;
  }
  return { agree_pairs: agree, true_statements: byD[0], max_run: maxRun, agree_by_distance: byD };
}

/**
 * Whether an ordering is balanced (cfg.shuffle), all bounds inclusive: the agreeing pairs overall
 * and at each distance 1..N−3, the true statements, and the longest run of statements in one
 * direction.
 * @param {number[]} ordering - o[c − 1] = world slot at context position c.
 * @param {object} cfg
 * @returns {boolean}
 */
export function isBalancedOrdering(ordering, cfg) {
  return passesBalance(ordering, shuffleBounds(ordering.length, cfg.shuffle));
}

/** isBalancedOrdering against precomputed bounds; creates no arrays (the sampler calls it most). */
function passesBalance(o, b) {
  const n = o.length;
  // True statements and the longest run of statements in one direction.
  let trueCount = 0; let run = 1;
  for (let c = 0; c < n - 1; c++) {
    const t = o[c] < o[c + 1];
    if (t) trueCount++;
    if (c > 0) {
      run = (t === (o[c - 1] < o[c])) ? run + 1 : 1;
      if (run > b.maxRun) return false;
    }
  }
  if (trueCount < b.trueLo || trueCount > b.trueHi) return false;
  // Agreeing pairs overall and at each d = 1..N−3.
  let agree = 0;
  for (let d = 1; d < n; d++) {
    let atD = 0;
    for (let i = 0; i + d < n; i++) if (o[i] < o[i + d]) atD++;
    agree += atD;
    if (d <= b.distances) {
      const frac = atD / (n - d);
      if (frac < b.perDistance[0] - EPS || frac > b.perDistance[1] + EPS) return false;
    }
  }
  return agree >= b.agreeLo && agree <= b.agreeHi;
}

/**
 * Rejection-sample uniform random orderings (Fisher–Yates of 1..N) until one is balanced and
 * puts the queried slots at the queried positions: o(a) = slotAtA and o(a + d) = slotAtAd. The
 * result is uniform over the balanced orderings with those slots (over all balanced orderings
 * when `query` is null).
 * @param {function(): number} rng - Stream `orderings`.
 * @param {?{a: number, d: number, slotAtA: number, slotAtAd: number}} query
 * @param {object} cfg
 * @returns {{ordering: number[], draws: number}}
 */
export function sampleShuffledOrdering(rng, query, cfg) {
  const n = cfg.slotCount;
  const bounds = shuffleBounds(n, cfg.shuffle);
  const o = new Array(n);
  for (let draws = 1; draws <= cfg.shuffle.maxDraws; draws++) {
    for (let c = 0; c < n; c++) o[c] = c + 1;          // a fresh copy of 1..N,
    shuffleInPlace(rng, o);                            // then one full Fisher–Yates
    if (query && (o[query.a - 1] !== query.slotAtA || o[query.a + query.d - 1] !== query.slotAtAd)) continue;
    if (passesBalance(o, bounds)) return { ordering: o.slice(), draws };
  }
  throw new Error(`[sampleShuffledOrdering] no balanced ordering for query ${JSON.stringify(query)} within ${cfg.shuffle.maxDraws} draws.`);
}

// --- Line order -------------------------------------------------------------

/**
 * Line-order statistics.
 * @param {number[]} sigma - sigma[i] = statement index (1-based) on screen line i + 1.
 * @returns {{chain_adjacencies: number, max_in_order_run: number, tau: number}}
 *   chain_adjacencies: lines i with |σ(i+1) − σ(i)| = 1; max_in_order_run:
 *   longest run of consecutive lines whose statement indices all step by +1,
 *   or all by −1 (1 when there is none); tau: Kendall τ between line index
 *   and statement index.
 */
export function lineOrderStats(sigma) {
  const n = sigma.length;
  let chain = 0; let best = 1; let run = 1; let dir = 0;
  for (let i = 1; i < n; i++) {
    const step = sigma[i] - sigma[i - 1];
    if (step === 1 || step === -1) {
      chain++;
      run = step === dir ? run + 1 : 2;
      dir = step;
    } else {
      run = 1;
      dir = 0;
    }
    if (run > best) best = run;
  }
  let concordant = 0; let discordant = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (sigma[j] > sigma[i]) concordant++;
      else if (sigma[j] < sigma[i]) discordant++;
    }
  }
  return { chain_adjacencies: chain, max_in_order_run: best, tau: (concordant - discordant) / ((n * (n - 1)) / 2) };
}

function acceptedStats(stats, lo) {
  return stats.chain_adjacencies <= lo.maxChainAdjacencies
    && stats.max_in_order_run <= lo.maxInOrderRun
    && Math.abs(stats.tau) < lo.maxAbsTau;
}

/**
 * The line-order rule: at most lineOrder.maxChainAdjacencies chain
 * adjacencies, no in-order run longer than lineOrder.maxInOrderRun, and
 * |τ| < lineOrder.maxAbsTau.
 * @param {number[]} sigma - Statement indices (1-based) in screen order.
 * @param {object} cfg
 * @returns {boolean}
 */
export function isAcceptedLineOrder(sigma, cfg) {
  return acceptedStats(lineOrderStats(sigma), cfg.lineOrder);
}

/**
 * Draw `count` distinct accepted line orders (uniform random orders of the
 * N − 1 statements, rejected if they break the line-order rule or repeat an
 * order already drawn).
 * @param {function(): number} rng - Stream `lines`.
 * @param {number} count
 * @param {object} cfg
 * @returns {{deck: number[][], draws: number}}
 */
export function sampleLineOrderDeck(rng, count, cfg) {
  const n = cfg.slotCount - 1;
  const sigma = new Array(n);
  const deck = [];
  const seen = new Set();
  let draws = 0;
  while (deck.length < count) {
    draws++;
    if (draws > cfg.lineOrder.maxDraws) {
      throw new Error(`[sampleLineOrderDeck] only ${deck.length} of ${count} distinct line orders within ${cfg.lineOrder.maxDraws} draws.`);
    }
    for (let i = 0; i < n; i++) sigma[i] = i + 1;      // a fresh copy of 1..N−1,
    shuffleInPlace(rng, sigma);                        // then one full Fisher–Yates
    if (!acceptedStats(lineOrderStats(sigma), cfg.lineOrder)) continue;
    const key = sigma.join(',');
    if (seen.has(key)) continue;
    seen.add(key);
    deck.push(sigma.slice());
  }
  return { deck, draws };
}

// --- Sequencing -------------------------------------------------------------

function capsHold(previous, candidate, caps) {
  const seq = previous.concat(candidate);
  const start = previous.length;
  for (const cap of caps) {
    let run = 0; let last;
    for (let i = 0; i < seq.length; i++) {
      const v = seq[i][cap.key];
      run = (i > 0 && v === last) ? run + 1 : 1;
      last = v;
      if (i >= start && run > cap.max) return false;
    }
  }
  return true;
}

function mainCaps(cfg) {
  return [
    { key: 'correct_answer_context', max: cfg.maxRun.correctSide },
    { key: 'context_distance', max: cfg.maxRun.contextDistance },
  ];
}

/**
 * Rejection-shuffle one block until every run cap holds, including across the boundary with the
 * previous block (correct side ≤ maxRun.correctSide, symbolic distance ≤
 * maxRun.contextDistance). Each attempt shuffles a fresh copy of `trials`. There is no cap on
 * runs of agree or conflict questions.
 * @param {function(): number} rng - Stream `sequence` (or `sequence:retry<n>`).
 * @param {object[]} trials - The block's records, in canonical order.
 * @param {object[]} previous - The previous block's final sequence ([] for block 1).
 * @param {object} cfg
 * @returns {{sequence: (object[]|null), attempts: number}} sequence is null
 *   when sequenceMaxAttempts attempts all failed.
 */
export function sequenceBlock(rng, trials, previous, cfg) {
  const caps = mainCaps(cfg);
  for (let attempt = 1; attempt <= cfg.sequenceMaxAttempts; attempt++) {
    const candidate = shuffled(rng, trials);
    if (capsHold(previous, candidate, caps)) return { sequence: candidate, attempts: attempt };
  }
  return { sequence: null, attempts: cfg.sequenceMaxAttempts };
}

// --- Items --------------------------------------------------------------------

/**
 * Query items (stream `items`). Every question queries world slots
 * (x, x + kd) and needs one item from each. Slot pairs are handled from the
 * tightest (questions ÷ available item pairs, then more questions, then
 * lower x, then lower y) to the loosest; each question (canonical order
 * within its slot pair) takes an unused item pair whose two items have the
 * lowest running query counts (sum, then maximum), uniformly among ties. So
 * no unordered item pair is queried twice.
 * @param {function(): number} rng - Stream `items` (or `items:retry<n>`).
 * @param {Array<{kd: number, x: number}>} questions
 * @param {string[][]} eligibleBySlot - eligibleBySlot[s − 1] = item IDs of slot s, in table
 *   order.
 * @returns {{pairs: Array<{low: string, high: string}>, queryCounts: Map<string, number>}}
 *   pairs[j].low is the item at world slot x, .high at x + kd.
 */
export function assignQueryItems(rng, questions, eligibleBySlot) {
  const groups = new Map();
  questions.forEach((q, j) => {
    const key = `${q.x}-${q.x + q.kd}`;
    if (!groups.has(key)) groups.set(key, { x: q.x, y: q.x + q.kd, idx: [] });
    groups.get(key).idx.push(j);
  });
  const avail = (g) => eligibleBySlot[g.x - 1].length * eligibleBySlot[g.y - 1].length;
  const order = [...groups.values()].sort((g, h) => (h.idx.length / avail(h)) - (g.idx.length / avail(g))
    || h.idx.length - g.idx.length || g.x - h.x || g.y - h.y);
  const counts = new Map();
  const used = new Set();
  const pairs = new Array(questions.length).fill(null);
  for (const g of order) {
    const lows = eligibleBySlot[g.x - 1];
    const highs = eligibleBySlot[g.y - 1];
    for (const j of g.idx) {
      let best = null; let ties = [];
      for (const lo of lows) {
        for (const hi of highs) {
          if (used.has(pairKey(lo, hi))) continue;
          const cl = counts.get(lo) || 0; const ch = counts.get(hi) || 0;
          const score = [cl + ch, Math.max(cl, ch)];
          const cmp = best === null ? -1 : (score[0] - best[0] || score[1] - best[1]);
          if (cmp < 0) { best = score; ties = [[lo, hi]]; } else if (cmp === 0) ties.push([lo, hi]);
        }
      }
      if (!ties.length) throw new Error(`[assignQueryItems] world slots (${g.x}, ${g.y}) ran out of distinct item pairs.`);
      const [lo, hi] = ties[randInt(rng, ties.length)];
      used.add(pairKey(lo, hi));
      counts.set(lo, (counts.get(lo) || 0) + 1);
      counts.set(hi, (counts.get(hi) || 0) + 1);
      pairs[j] = { low: lo, high: hi };
    }
  }
  return { pairs, queryCounts: counts };
}

/** Largest minus smallest query count within any queried slot (0 when perfectly even). */
function querySpread(questions, queryCounts, eligibleBySlot) {
  const slots = new Set();
  for (const q of questions) { slots.add(q.x); slots.add(q.x + q.kd); }
  let worst = 0;
  for (const s of slots) {
    const cs = eligibleBySlot[s - 1].map((id) => queryCounts.get(id) || 0);
    worst = Math.max(worst, Math.max(...cs) - Math.min(...cs));
  }
  return worst;
}

/**
 * Context items (stream `items`, after assignQueryItems). For each world slot
 * s = 1..N with n eligible items: each item's total appearances (queried or
 * not) is ⌊Q/n⌋ or ⌈Q/n⌉. Items whose query count already exceeds ⌊Q/n⌋ take
 * a ⌈Q/n⌉ total; the other ⌈Q/n⌉ totals go to the first items of a shuffle
 * of the rest (table order). Each item's remaining count forms a deck
 * (table order), shuffled once and dealt, in canonical order, to the
 * questions that do not query slot s.
 * @param {function(): number} rng - The same stream as assignQueryItems.
 * @param {Array<{kd: number, x: number}>} questions
 * @param {Array<{low: string, high: string}>} pairs - From assignQueryItems.
 * @param {string[][]} eligibleBySlot
 * @returns {string[][]} items[j][s − 1] = item ID at world slot s in question j.
 */
export function dealContextItems(rng, questions, pairs, eligibleBySlot) {
  const N = eligibleBySlot.length;
  const Q = questions.length;
  const items = questions.map(() => new Array(N).fill(null));
  questions.forEach((q, j) => {
    items[j][q.x - 1] = pairs[j].low;
    items[j][q.x + q.kd - 1] = pairs[j].high;
  });
  for (let s = 1; s <= N; s++) {
    const ids = eligibleBySlot[s - 1];
    const n = ids.length;
    const qc = new Map(ids.map((id) => [id, 0]));
    items.forEach((row, j) => {
      const q = questions[j];
      if (s === q.x || s === q.x + q.kd) qc.set(row[s - 1], qc.get(row[s - 1]) + 1);
    });
    const floor = Math.floor(Q / n);
    const extra = Q - floor * n;
    const forced = ids.filter((id) => qc.get(id) > floor);
    if (forced.some((id) => qc.get(id) > floor + 1) || forced.length > extra) {
      throw new Error(`[dealContextItems] slot ${s}: query counts ${ids.map((id) => qc.get(id))} leave no ⌊Q/n⌋/⌈Q/n⌉ totals.`);
    }
    const rest = shuffled(rng, ids.filter((id) => !forced.includes(id)));
    const ceil = new Set([...forced, ...rest.slice(0, extra - forced.length)]);
    const deck = [];
    for (const id of ids) {
      const total = floor + (ceil.has(id) ? 1 : 0);
      for (let k = qc.get(id); k < total; k++) deck.push(id);
    }
    const cards = shuffled(rng, deck);
    let next = 0;
    items.forEach((row) => { if (row[s - 1] === null) row[s - 1] = cards[next++]; });
    if (next !== cards.length) throw new Error(`[dealContextItems] slot ${s}: dealt ${next} of ${cards.length} cards.`);
  }
  return items;
}

// --- Text ---------------------------------------------------------------------

function capitalizeFirst(s) {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

/**
 * One statement: "{Subject} {relation_phrase} {object}." with the subject
 * capitalized at the start of the sentence.
 * @param {string} subjectLabel - Lower-case label with article, e.g. "the horse".
 * @param {string} relationPhrase - e.g. "is heavier than".
 * @param {string} objectLabel - e.g. "the dog".
 * @returns {string} e.g. "The horse is heavier than the dog."
 */
export function renderStatement(subjectLabel, relationPhrase, objectLabel) {
  return `${capitalizeFirst(subjectLabel)} ${relationPhrase} ${objectLabel}.`;
}

function tableItemLabel(item) {
  return item.article ? `${item.article} ${item.name}` : item.name;
}

// --- Canonical JSON and hashing -------------------------------------------------

/**
 * Canonical JSON: object keys sorted, no whitespace; otherwise JSON.stringify
 * semantics (undefined object members are dropped, undefined array entries
 * become null). Non-finite numbers throw.
 * @param {*} value
 * @returns {string}
 */
export function canonicalJson(value) {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('[canonicalJson] non-finite number.');
    return JSON.stringify(value);
  }
  if (typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((v) => canonicalJson(v)).join(',')}]`;
  const keys = Object.keys(value).filter((k) => value[k] !== undefined).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
}

async function sha256Hex(text) {
  const subtle = globalThis.crypto && globalThis.crypto.subtle;
  if (!subtle) throw new Error('[buildSession] crypto.subtle is unavailable.');
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

// --- Scoring --------------------------------------------------------------------

/**
 * Score one question from its saved row (the record plus the plugin's
 * `response`). Pure: returns the three fields; the trial's on_finish copies
 * them into the row (Object.assign(data, scoreResponse(data))). Throws when
 * `response` is anything but 'left', 'right' or null (a timeout).
 *
 *   timeout (response null) → chosen_item null, is_correct false,
 *                             is_knowledge_consistent null;
 *   otherwise               → is_correct = response === correct_answer_context;
 *                             is_knowledge_consistent = response === knowledge_answer.
 *
 * @param {{response: ?string, query_left_item: string, query_right_item: string,
 *   correct_answer_context: string, knowledge_answer: string}} data
 * @returns {{chosen_item: ?string, is_correct: boolean, is_knowledge_consistent: ?boolean}}
 */
export function scoreResponse(data) {
  const response = data.response;
  if (response !== null && response !== 'left' && response !== 'right') {
    throw new Error(`[scoreResponse] response must be 'left', 'right' or null (timeout); got ${JSON.stringify(response)}.`);
  }
  if (response === null) return { chosen_item: null, is_correct: false, is_knowledge_consistent: null };
  return {
    chosen_item: response === 'left' ? data.query_left_item : data.query_right_item,
    is_correct: response === data.correct_answer_context,
    is_knowledge_consistent: response === data.knowledge_answer,
  };
}

// --- Records and display strings --------------------------------------------

function indexDomains(tables, cfg) {
  const map = new Map();
  for (const def of tables.domains) {
    const slots = def.slot_tables && def.slot_tables[String(cfg.slotCount)];
    if (!Array.isArray(slots) || slots.some((s) => typeof s !== 'object')) continue;
    const byId = new Map();
    const eligibleBySlot = [];
    for (const s of slots) {
      eligibleBySlot[s.slot - 1] = s.items.filter((it) => it.eligible === true);
      for (const it of s.items) byId.set(it.item_id, { ...it, slot: s.slot });
    }
    map.set(def.domain_id, { def, byId, eligibleBySlot });
  }
  return map;
}

function domainOf(domains, id, role) {
  const dom = domains.get(id);
  if (!dom) throw new Error(`[buildSession] domains.${role} '${id}' has no usable slot table.`);
  return dom;
}

/** The record columns, in order (every question row has all of them). */
function emptyRecord() {
  return {
    phase: null, trial_number: null, block_index: null,
    ordering_type: null, query_congruence: null, domain: null, relation_word: null,
    context_distance: null, knowledge_distance: null, scale_position_bin: null,
    query_left_item: null, query_right_item: null, query_left_text: null, query_right_text: null,
    query_left_context_position: null, query_right_context_position: null,
    query_left_slot: null, query_right_slot: null,
    correct_answer_context: null, knowledge_answer: null, item_pair_key: null,
    context_ordering_json: null, context_slots_json: null, statements_text_json: null,
    statements_char_count: null, line_order_json: null, path_line_positions_json: null,
    path_agree_links: null, ordering_agree_pairs: null, ordering_true_statements: null,
    ordering_max_run: null, line_order_chain_adjacencies: null, line_order_max_in_order_run: null,
    line_order_tau: null,
  };
}

/**
 * Build one question from its specification:
 *   spec.positions[c − 1] = {id, label} of the item at context position c;
 *   spec.ordering = world slots by context position;
 *   spec.a = context position of the lower queried item; spec.d;
 *   spec.sigma = line order (1-based); spec.side = correct-answer side.
 */
function buildQuestion(spec, domainDef, cfg) {
  const N = cfg.slotCount;
  const { positions, ordering, a, d, sigma, side } = spec;
  const texts = range(1, N - 1).map((c) => renderStatement(positions[c].label, domainDef.relation_phrase, positions[c - 1].label));
  const statements = sigma.map((s) => texts[s - 1]);
  const hi = a + d;                                    // context position of the statements' answer
  const leftPos = side === 'left' ? hi : a;
  const rightPos = side === 'left' ? a : hi;
  const slotAt = (c) => ordering[c - 1];
  const knowledgeSide = (slotAt(hi) > slotAt(a)) === (side === 'left') ? 'left' : 'right';
  const stats = orderingStats(ordering);
  const lineStats = lineOrderStats(sigma);
  const path = range(a, hi - 1);
  const rec = emptyRecord();
  Object.assign(rec, {
    domain: domainDef.domain_id,
    relation_word: domainDef.query_emphasis,
    context_distance: d,
    knowledge_distance: Math.abs(slotAt(hi) - slotAt(a)),
    query_left_item: positions[leftPos - 1].id,
    query_right_item: positions[rightPos - 1].id,
    query_left_text: positions[leftPos - 1].label,
    query_right_text: positions[rightPos - 1].label,
    query_left_context_position: leftPos,
    query_right_context_position: rightPos,
    query_left_slot: slotAt(leftPos),
    query_right_slot: slotAt(rightPos),
    correct_answer_context: side,
    knowledge_answer: knowledgeSide,
    item_pair_key: pairKey(positions[a - 1].id, positions[hi - 1].id),
    context_ordering_json: JSON.stringify(positions.map((p) => p.id)),
    context_slots_json: JSON.stringify(ordering),
    statements_text_json: JSON.stringify(statements),
    statements_char_count: statements.reduce((n, t) => n + t.length, 0),
    line_order_json: JSON.stringify(sigma),
    path_line_positions_json: JSON.stringify(path.map((c) => sigma.indexOf(c) + 1)),
    path_agree_links: path.filter((c) => ordering[c] > ordering[c - 1]).length,
    ordering_agree_pairs: stats.agree_pairs,
    ordering_true_statements: stats.true_statements,
    ordering_max_run: stats.max_run,
    line_order_chain_adjacencies: lineStats.chain_adjacencies,
    line_order_max_in_order_run: lineStats.max_in_order_run,
    line_order_tau: lineStats.tau,
  });
  return { rec, statements, question_html: questionCopy(cfg, domainDef) };
}

/** The question-trial plugin's parameters for a built question. */
function questionParams(q, cfg) {
  return {
    question_html: q.question_html,
    left_label: q.rec.query_left_text,
    right_label: q.rec.query_right_text,
    statements: q.statements.slice(),
    deadline_ms: cfg.responseDeadlineMs,
    confirmation_min_ms: framesToMs(cfg.timing.confirmationMinFrames, cfg),
  };
}

// --- Balance exactness ------------------------------------------------------------

function countBy(items, keyFn) {
  const m = new Map();
  for (const it of items) {
    const k = keyFn(it);
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

/** 'exact' when every count is equal, 'pm1' when they differ by at most 1, else null. */
function spreadStatus(counts) {
  if (!counts.length) return 'exact';
  const spread = Math.max(...counts) - Math.min(...counts);
  return spread === 0 ? 'exact' : spread <= 1 ? 'pm1' : null;
}

/** The weaker of several statuses (exact < pm1); null or false (a failure) wins. */
function weakest(...statuses) {
  if (statuses.some((x) => x === null || x === false)) return null;
  return statuses.includes('pm1') ? 'pm1' : 'exact';
}

/** The count of each key (0 for a key no item has). */
function gridCounts(items, keyFn, keys) {
  const m = countBy(items, keyFn);
  return keys.map((k) => m.get(k) || 0);
}

/** A multiset as a sorted, joined string. */
function multiset(values) {
  return values.map(String).sort().join(',');
}

/**
 * balance_exactness, computed from the built main records: each key is 'exact' (every count of
 * its grid is the same, or the property holds exactly) or 'pm1' (counts differ by at most 1);
 * anything else makes the build throw. Keys for both conditions: distance_counts,
 * knowledge_distance_counts, knowledge_by_distance, skeleton, blocks, sides,
 * query_pairs_unique, query_items_by_slot, items_by_slot,
 * line_orders_distinct. Shuffled only: mirror_split,
 * distance_by_knowledge_distance.
 */
function computeBalanceExactness(main, condition, skeleton, eligibleBySlot, cfg) {
  const N = cfg.slotCount;
  const D = N - 3;
  const { m } = skeleton;
  const B = main.length / (2 * D);
  const ds = range(1, D);
  const lowPos = (r) => Math.min(r.query_left_context_position, r.query_right_context_position);
  const lowSlot = (r) => Math.min(r.query_left_slot, r.query_right_slot);
  const shuffledCond = condition === 'shuffled';
  const out = {};
  const set = (key, status) => {
    if (status !== 'exact' && status !== 'pm1') throw new Error(`[buildSession] balance property '${key}' failed.`);
    out[key] = status;
  };
  const exactIf = (ok) => (ok ? 'exact' : null);

  set('distance_counts', exactIf(gridCounts(main, (r) => r.context_distance, ds).every((n) => n === m)));
  set('knowledge_distance_counts', exactIf(gridCounts(main, (r) => r.knowledge_distance, ds).every((n) => n === m)));
  const right = (r) => r.knowledge_answer === r.correct_answer_context;
  if (!shuffledCond) set('knowledge_by_distance', exactIf(main.every(right) && main.every((r) => r.query_congruence === 'agree')));
  else {
    const half = (key) => ds.every((v) => {
      const rows = main.filter((r) => r[key] === v);
      return rows.filter(right).length * 2 === rows.length
        && rows.every((r) => right(r) === (r.query_congruence === 'agree'));
    });
    set('knowledge_by_distance', exactIf(half('context_distance') && half('knowledge_distance')));
  }
  const expectPos = multiset(skeleton.picks.flatMap((picks, i) => picks.map((p) => `${i + 1}:${p.a}`)));
  const gotPos = multiset(main.map((r) => `${r.context_distance}:${lowPos(r)}`));
  const gotSlot = multiset(main.map((r) => `${r.knowledge_distance}:${lowSlot(r)}`));
  set('skeleton', exactIf(gotPos === expectPos && gotSlot === expectPos));
  const labels = shuffledCond ? ['agree', 'conflict'] : ['agree'];
  const perLabel = 2 / labels.length;
  const blocksOk = range(1, B).every((b) => ds.every((d) => labels.every((lab) => main.filter((r) => r.block_index === b
    && r.context_distance === d && r.query_congruence === lab).length === perLabel)));
  set('blocks', exactIf(blocksOk));
  const pairSides = range(1, B).every((b) => ds.every((d) => {
    const rows = main.filter((r) => r.block_index === b && r.context_distance === d);
    return rows.length === 2 && rows.filter((r) => r.correct_answer_context === 'left').length === 1;
  }));
  let sidesStatus = exactIf(pairSides);
  if (shuffledCond) {
    const agreeLeft = main.filter((r) => r.query_congruence === 'agree' && r.correct_answer_context === 'left');
    const perBlock = gridCounts(agreeLeft, (r) => r.block_index, range(1, B)).every((n) => n * 2 === D);
    // At every d the agree (and so the conflict) questions are left in B/2 blocks: exact when B
    // is even, ±1 when it is odd.
    const leftByD = gridCounts(agreeLeft, (r) => r.context_distance, ds);
    sidesStatus = weakest(sidesStatus, exactIf(perBlock), spreadStatus(leftByD.flatMap((n) => [n, B - n])));
  }
  set('sides', sidesStatus);
  const keys = main.map((r) => r.item_pair_key);
  set('query_pairs_unique', exactIf(new Set(keys).size === keys.length));
  const queryCounts = new Map();
  const totals = new Map();
  for (const r of main) {
    for (const id of [r.query_left_item, r.query_right_item]) queryCounts.set(id, (queryCounts.get(id) || 0) + 1);
    for (const id of JSON.parse(r.context_ordering_json)) totals.set(id, (totals.get(id) || 0) + 1);
  }
  const queried = new Set(main.flatMap((r) => [r.query_left_slot, r.query_right_slot]));
  set('query_items_by_slot', weakest(...[...queried].map((s) => spreadStatus(eligibleBySlot[s - 1].map((id) => queryCounts.get(id) || 0)))));
  set('items_by_slot', weakest(...eligibleBySlot.map((ids) => spreadStatus(ids.map((id) => totals.get(id) || 0)))));
  const lines = main.map((r) => r.line_order_json);
  set('line_orders_distinct', exactIf(new Set(lines).size === lines.length));
  if (shuffledCond) {
    // Each mirror group at a distance sends as many picks to agree as to conflict.
    const groupOf = (v, delta) => Math.min(v, N + 1 - v - delta);
    const splitOk = (key, posFn) => ds.every((delta) => {
      const rows = main.filter((r) => r[key] === delta);
      const agree = countBy(rows.filter((r) => r.query_congruence === 'agree'), (r) => groupOf(posFn(r), delta));
      const conflict = countBy(rows.filter((r) => r.query_congruence === 'conflict'), (r) => groupOf(posFn(r), delta));
      return [...new Set([...agree.keys(), ...conflict.keys()])].every((g) => agree.get(g) === conflict.get(g));
    });
    set('mirror_split', exactIf(splitOk('context_distance', lowPos) && splitOk('knowledge_distance', lowSlot)));
    set('distance_by_knowledge_distance', spreadStatus(gridCounts(main, (r) => `${r.context_distance}|${r.knowledge_distance}`,
      ds.flatMap((d) => ds.map((kd) => `${d}|${kd}`)))));
  }
  return out;
}

// --- Assignment rows -----------------------------------------------------------------

/**
 * The assignment row of a session. Pure: randomness comes from `rand`.
 * - `assignmentId` given: the row with that `assignment_id`; an id that is not a row throws.
 * - Otherwise: a uniform choice (`rand`) among the rows.
 * @param {Array<{assignment_id: number, condition: string}>} rows
 * @param {?number} assignmentId
 * @param {function(): number} rand - Uniform in [0, 1).
 * @returns {{assignment_id: number, condition: string}} A copy of the row.
 */
export function resolveAssignmentRow(rows, assignmentId, rand) {
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('[resolveAssignmentRow] the assignment table has no rows.');
  if (assignmentId !== null && assignmentId !== undefined) {
    const row = rows.find((r) => r.assignment_id === assignmentId);
    if (!row) throw new Error(`Assignment ${assignmentId} is not a row of data/assignments.json.`);
    return { ...row };
  }
  return { ...rows[Math.floor(rand() * rows.length)] };
}

// --- buildSession -------------------------------------------------------------------

/**
 * Build every question of one session. The stages run in this call order, each on its own
 * stream: skeleton, knowledge (shuffled only), blocks, sides, orderings (shuffled only), lines,
 * items, sequence. The result is a pure function of (assignment_id, condition, cfg, tables).
 *
 * @param {{assignment_id: number, condition: string}} assignment
 *   - The assignment row (assignment_id seeds every stream).
 * @param {object} cfg - CONFIG (validated with validateConfig first).
 * @param {object} tables - Parsed item tables.
 * @returns {Promise<{
 *   assignment_id: number, condition: string,
 *   main: Array<{params: object, record: object}>,
 *   schedule: object[], schedule_sha256: string,
 *   balance_exactness: Object<string, string>, generation_stats: object,
 *   item_table_version: string, item_table_hash: ?string,
 * }>} Each question's `params` are the question-trial plugin parameters; its `record` goes in
 *   the node's `data`. `schedule` (the records in session order) is hashed into
 *   `schedule_sha256`, not saved.
 */
export async function buildSession(assignment, cfg, tables) {
  const { assignment_id: assignmentId, condition } = assignment || {};
  if (!Number.isInteger(assignmentId) || assignmentId < 0) {
    throw new Error(`[buildSession] assignment_id must be a non-negative integer (got ${JSON.stringify(assignmentId)}).`);
  }
  if (!CONDITIONS.includes(condition)) {
    throw new Error(`[buildSession] condition must be one of ${JSON.stringify(CONDITIONS)} (got ${JSON.stringify(condition)}).`);
  }
  const N = cfg.slotCount;
  const D = N - 3;
  const stream = (label) => makeStream(assignmentId, label);
  const domains = indexDomains(tables, cfg);
  const mainDom = domainOf(domains, cfg.domains.main, 'main');
  const eligibleIds = mainDom.eligibleBySlot.map((list) => list.map((it) => it.item_id));

  // 1. skeleton
  const skeleton = sampleSkeleton(stream('skeleton'), cfg);
  const Q = skeleton.m * D;
  const B = Q / (2 * D);
  // 2. knowledge
  let knowledge = null;
  let questions;
  if (condition === 'congruent') questions = congruentQuestions(skeleton);
  else {
    knowledge = assignKnowledgeDistances(stream('knowledge'), skeleton, cfg);
    questions = knowledge.questions;
  }
  // 3. blocks
  const blocks = assignBlocks(stream('blocks'), questions, cfg);
  // 4. sides
  const { sides, draws: sideDraws } = assignSides(stream('sides'), questions, blocks, cfg);
  // 5. orderings (canonical order)
  const orderingsRng = stream('orderings');
  const shuffleDraws = [];
  const orderings = questions.map((q) => {
    if (condition === 'congruent') return range(1, N);
    const [atA, atAd] = q.congruence === 'agree' ? [q.x, q.x + q.kd] : [q.x + q.kd, q.x];
    const res = sampleShuffledOrdering(orderingsRng, { a: q.a, d: q.d, slotAtA: atA, slotAtAd: atAd }, cfg);
    shuffleDraws.push(res.draws);
    return res.ordering;
  });
  // 6. lines: Q distinct accepted orders, dealt in canonical order
  const { deck: sigmas, draws: lineDraws } = sampleLineOrderDeck(stream('lines'), Q, cfg);
  // 7. items (reseeded while some slot's query counts differ by more than 1)
  let itemReseeds = 0;
  let query;
  for (;;) {
    const rng = stream(itemReseeds ? `items:retry${itemReseeds}` : 'items');
    query = assignQueryItems(rng, questions, eligibleIds);
    if (querySpread(questions, query.queryCounts, eligibleIds) <= 1) {
      query.items = dealContextItems(rng, questions, query.pairs, eligibleIds);
      break;
    }
    itemReseeds++;
    if (itemReseeds > cfg.sequenceMaxReseeds) throw new Error(`[buildSession] no ±1 query-item balance after ${cfg.sequenceMaxReseeds} reseeds.`);
  }

  // Records (unsequenced), in canonical order.
  const planned = questions.map((q, j) => {
    const positions = orderings[j].map((s) => {
      const it = mainDom.byId.get(query.items[j][s - 1]);
      return { id: it.item_id, label: tableItemLabel(it) };
    });
    const built = buildQuestion({ positions, ordering: orderings[j], a: q.a, d: q.d, sigma: sigmas[j], side: sides[j] }, mainDom.def, cfg);
    Object.assign(built.rec, {
      phase: 'main',
      block_index: blocks[j],
      ordering_type: condition,
      query_congruence: q.congruence,
      scale_position_bin: q.xBin,
    });
    return built;
  });

  // 8. sequence, block by block
  let seqRng = stream('sequence');
  let reseeds = 0;
  const sequenceAttempts = [];
  const mainOrder = [];
  let previous = [];
  for (let b = 1; b <= B; b++) {
    const blockTrials = planned.filter((q) => q.rec.block_index === b).map((q) => q.rec);
    let attempts = 0;
    let result;
    for (;;) {
      result = sequenceBlock(seqRng, blockTrials, previous, cfg);
      attempts += result.attempts;
      if (result.sequence) break;
      reseeds++;
      if (reseeds > cfg.sequenceMaxReseeds) {
        throw new Error(`[buildSession] block ${b} could not be sequenced after ${cfg.sequenceMaxReseeds} reseeds.`);
      }
      seqRng = stream(`sequence:retry${reseeds}`);
    }
    sequenceAttempts.push(attempts);
    mainOrder.push(...result.sequence);
    previous = result.sequence;
  }
  mainOrder.forEach((rec, k) => { rec.trial_number = k + 1; });
  const byRec = new Map(planned.map((q) => [q.rec, q]));
  const main = mainOrder.map((rec) => ({ params: questionParams(byRec.get(rec), cfg), record: rec }));

  const balance_exactness = computeBalanceExactness(mainOrder, condition, skeleton, eligibleIds, cfg);
  const schedule = main.map((t) => ({ ...t.record }));
  const schedule_sha256 = await sha256Hex(canonicalJson(schedule));

  return {
    assignment_id: assignmentId,
    condition,
    main,
    schedule,
    schedule_sha256,
    balance_exactness,
    generation_stats: {
      latin_square_draws: knowledge ? knowledge.draws : 0,
      shuffle_draws_total: shuffleDraws.reduce((s, x) => s + x, 0),
      shuffle_draws_max: shuffleDraws.length ? Math.max(...shuffleDraws) : 0,
      side_draws: sideDraws,
      item_reseeds: itemReseeds,
      line_order_draws: lineDraws,
      sequence_attempts: sequenceAttempts,
      sequence_reseeds: reseeds,
    },
    item_table_version: tables.table_version,
    item_table_hash: tables.source_hash || null,
  };
}
