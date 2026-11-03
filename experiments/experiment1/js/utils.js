/**
 * Helpers for building trials: random draws, pairs and distances in an ordering, the
 * distance-balanced test pairs, scheduling without repeats, the displayed chain with its
 * distractors and its window, the sequence constraints of learning and practice, and labels.
 *
 * Every random draw goes through Math.random, which the experiment replaces by its seeded
 * generator (seeded-rng.js).
 *
 * @module utils
 */

import { CONFIG } from './config.js';

// --- Random draws ---

/**
 * Fisher-Yates shuffle in place: one draw per element after the first.
 * @param {Array} arr
 * @returns {Array} The same array, shuffled.
 */
export function shuffleArray(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/**
 * A shuffled copy of the array; the original is unchanged.
 * @param {Array} arr
 * @returns {Array}
 */
export function shuffledCopy(arr) {
  return shuffleArray([...arr]);
}

/**
 * The indices 0 to n - 1 in a random order.
 * @param {number} n
 * @returns {number[]}
 */
export function shuffledIndices(n) {
  return shuffledCopy(Array.from({ length: n }, (_, i) => i));
}

/**
 * A random integer in [min, max] (inclusive).
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * One element drawn uniformly at random.
 * @param {Array} arr
 * @returns {*}
 */
export function randomChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// --- Pairs and distances ---

/**
 * All pairs of items at a given symbolic distance in an ordering.
 * @param {string[]} ordering - Item IDs, highest to lowest.
 * @param {number} distance - Symbolic distance (1 to numItems - 1).
 * @returns {Array<[string, string]>} [higherItem, lowerItem] pairs.
 */
export function getPairsAtDistance(ordering, distance) {
  const pairs = [];
  for (let i = 0; i < ordering.length - distance; i++) {
    pairs.push([ordering[i], ordering[i + distance]]);
  }
  return pairs;
}

/**
 * The rank pairs of one test, balanced over symbolic distance.
 *
 *   1. Every one of the N(N-1)/2 rank pairs appears once (21 at N = 7).
 *   2. The remaining trials are spread over the N-1 distances as evenly as possible; the
 *      remainder goes to randomly chosen distances. With N = 7 and 40 trials, 19 extra trials
 *      give 3 per distance and one more to one distance.
 *   3. Within a distance, its extra trials are spread over its rank pairs as evenly as
 *      possible, the remainder again to randomly chosen pairs. At 40 trials no rank pair
 *      appears more than five times (the single pair at distance 6), the number of ICL
 *      orderings.
 *
 * The result is shuffled.
 *
 * @param {number} rankCount - Number of ranks (N).
 * @param {number} totalTrials - Number of trials.
 * @returns {Array<{higherRank: number, lowerRank: number, distance: number, pairCategory: string}>}
 */
export function generateDistanceUniformPairs(rankCount, totalTrials) {
  const numDistances = rankCount - 1;
  const allByDistance = [];
  for (let d = 1; d <= numDistances; d++) {
    const atD = [];
    for (let h = 1; h + d <= rankCount; h++) {
      atD.push({ higherRank: h, lowerRank: h + d, distance: d });
    }
    allByDistance.push(atD);
  }

  const baseCount = allByDistance.reduce((sum, p) => sum + p.length, 0);
  if (totalTrials < baseCount) {
    throw new Error(
      `generateDistanceUniformPairs: totalTrials=${totalTrials} is below the ` +
      `${baseCount} base counts required for full pair coverage at N=${rankCount}.`
    );
  }
  const extras = totalTrials - baseCount;
  const baseExtrasPerDistance = Math.floor(extras / numDistances);
  const remainderExtras = extras - baseExtrasPerDistance * numDistances;

  const distanceOrder = shuffledIndices(numDistances).map((i) => i + 1);
  const plusOneDistances = new Set(distanceOrder.slice(0, remainderExtras));

  const out = [];
  for (let d = 1; d <= numDistances; d++) {
    const dPairs = allByDistance[d - 1];
    for (const p of dPairs) out.push({ ...p });

    const dExtras = baseExtrasPerDistance + (plusOneDistances.has(d) ? 1 : 0);
    if (dExtras === 0) continue;

    const baseExtraPerPair = Math.floor(dExtras / dPairs.length);
    const rem = dExtras - baseExtraPerPair * dPairs.length;
    const pairOrder = shuffledIndices(dPairs.length);
    const plusOnePairs = new Set(pairOrder.slice(0, rem));
    for (let pIdx = 0; pIdx < dPairs.length; pIdx++) {
      const extras = baseExtraPerPair + (plusOnePairs.has(pIdx) ? 1 : 0);
      for (let k = 0; k < extras; k++) out.push({ ...dPairs[pIdx] });
    }
  }

  for (const t of out) {
    t.pairCategory = `${t.higherRank}_${t.lowerRank}`;
  }
  return shuffleArray(out);
}

// --- Test scheduling without repeats ---

/**
 * Reorder `trials` so that no two neighbors share `keyOf(trial)`. Greedy: each step takes the
 * key with the most trials left among the keys other than the previous one (ties: first in
 * insertion order). A neighbor pair left with the same key is then repaired by swapping with a
 * trial elsewhere. No random draws.
 *
 * @param {Array<object>} trials
 * @param {(t: object) => string} keyOf
 * @returns {Array<object>} A new array; the input is unchanged.
 */
export function scheduleNoConsecutive(trials, keyOf) {
  const remaining = new Map();
  for (const t of trials) {
    const k = keyOf(t);
    if (!remaining.has(k)) remaining.set(k, []);
    remaining.get(k).push(t);
  }
  const out = [];
  let prevKey = null;
  while (out.length < trials.length) {
    let bestKey = null;
    let bestCount = -1;
    for (const [k, arr] of remaining) {
      if (k === prevKey) continue;
      if (arr.length > bestCount) {
        bestCount = arr.length;
        bestKey = k;
      }
    }
    if (bestKey === null) {
      // Only the previous key is left: take it; the repair pass below fixes the repeat.
      for (const [k, arr] of remaining) {
        if (arr.length > 0) { bestKey = k; break; }
      }
    }
    const arr = remaining.get(bestKey);
    out.push(arr.shift());
    if (arr.length === 0) remaining.delete(bestKey);
    prevKey = bestKey;
  }

  for (let i = 1; i < out.length; i++) {
    if (keyOf(out[i]) !== keyOf(out[i - 1])) continue;
    let fixed = false;
    for (let j = 0; j < out.length; j++) {
      if (j === i || j === i - 1) continue;
      const ok =
        keyOf(out[j]) !== keyOf(out[i - 1]) &&
        (i + 1 >= out.length || keyOf(out[j]) !== keyOf(out[i + 1])) &&
        (j === 0 || keyOf(out[i]) !== keyOf(out[j - 1])) &&
        (j === out.length - 1 || keyOf(out[i]) !== keyOf(out[j + 1]));
      if (ok) {
        [out[i], out[j]] = [out[j], out[i]];
        fixed = true;
        break;
      }
    }
    if (!fixed) {
      console.warn(
        `scheduleNoConsecutive: could not resolve adjacent same-key pair at ` +
        `index ${i} (key=${keyOf(out[i])}).`
      );
    }
  }

  return out;
}

/**
 * Reorder `trials` so that no two neighbors share either `keyAOf(trial)` or `keyBOf(trial)`
 * (the ICL test: neither the ordering nor the rank pair repeats). Greedy: each step takes the
 * trial that differs from the previous one on the most keys, and among those the one whose key
 * has the most trials left (ties: first in the remaining pool). A repair pass then swaps away
 * any remaining repeat. No random draws.
 *
 * @param {Array<object>} trials
 * @param {(t: object) => string} keyAOf
 * @param {(t: object) => string} keyBOf
 * @returns {Array<object>}
 */
export function scheduleNoConsecutiveTwoKey(trials, keyAOf, keyBOf) {
  const remainingA = new Map();
  const remainingB = new Map();
  const pool = [...trials];
  for (const t of pool) {
    remainingA.set(keyAOf(t), (remainingA.get(keyAOf(t)) || 0) + 1);
    remainingB.set(keyBOf(t), (remainingB.get(keyBOf(t)) || 0) + 1);
  }

  const out = [];
  let prevA = null;
  let prevB = null;
  while (pool.length > 0) {
    let pickIdx = -1;
    let bestScore = -Infinity;
    for (let i = 0; i < pool.length; i++) {
      const a = keyAOf(pool[i]);
      const b = keyBOf(pool[i]);
      const okA = a !== prevA;
      const okB = b !== prevB;
      const tier = (okA ? 1 : 0) + (okB ? 1 : 0);
      const tieBreak = Math.max(remainingA.get(a) || 0, remainingB.get(b) || 0);
      const score = tier * 1e6 + tieBreak;
      if (score > bestScore) {
        bestScore = score;
        pickIdx = i;
      }
    }
    const t = pool.splice(pickIdx, 1)[0];
    const a = keyAOf(t);
    const b = keyBOf(t);
    remainingA.set(a, remainingA.get(a) - 1);
    remainingB.set(b, remainingB.get(b) - 1);
    out.push(t);
    prevA = a;
    prevB = b;
  }

  for (let i = 1; i < out.length; i++) {
    const a = keyAOf(out[i]);
    const b = keyBOf(out[i]);
    if (a !== keyAOf(out[i - 1]) && b !== keyBOf(out[i - 1])) continue;
    let fixed = false;
    for (let j = 0; j < out.length; j++) {
      if (j === i || j === i - 1) continue;
      const ja = keyAOf(out[j]);
      const jb = keyBOf(out[j]);
      // out[j] moves to position i and out[i] to position j; neither may match its new
      // neighbors.
      const ok =
        ja !== keyAOf(out[i - 1]) && jb !== keyBOf(out[i - 1]) &&
        (i + 1 >= out.length ||
          (ja !== keyAOf(out[i + 1]) && jb !== keyBOf(out[i + 1]))) &&
        (j === 0 ||
          (a !== keyAOf(out[j - 1]) && b !== keyBOf(out[j - 1]))) &&
        (j === out.length - 1 ||
          (a !== keyAOf(out[j + 1]) && b !== keyBOf(out[j + 1])));
      if (ok) {
        [out[i], out[j]] = [out[j], out[i]];
        fixed = true;
        break;
      }
    }
    if (!fixed) {
      console.warn(
        `scheduleNoConsecutiveTwoKey: could not resolve adjacent constraint at ` +
        `index ${i} (a=${a}, b=${b}).`
      );
    }
  }

  return out;
}

// --- The displayed chain ---

/**
 * Insert two distractors into an ordering, each into a gap and drawn from that gap's rank
 * bucket (buckets count from the top of `ordering`), so that in the learning phase a
 * distractor is always shown at the same place relative to the main items.
 *
 * Gaps: -1 above ordering[0]; g = 0 .. N-2 between ordering[g] and ordering[g + 1]; N-1 below
 * the last item. `targetDistractorsBetween` (0, 1 or 2) is how many of the two distractors go
 * between the two queried items: 0, both in other gaps; 1, one between and one outside; 2,
 * both between, in two different gaps, or stacked in the one gap of an adjacent pair.
 *
 * @param {string[]} ordering - Item IDs, highest to lowest.
 * @param {string} queryItem1 - A queried item.
 * @param {string} queryItem2 - The other queried item.
 * @param {number} targetDistractorsBetween - 0, 1 or 2.
 * @param {function} drawFn - (bucketName, excludeIds) -> distractor ID.
 * @param {function} drawTwoFn - (bucketName, excludeIds) -> two IDs, higher first.
 * @returns {{chain: string[], links: Array<{higher: string, lower: string}>,
 *   distractorPositions: number[], distractorIds: string[], distractorRankBuckets: string[]}}
 */
export function buildAugmentedChain(ordering, queryItem1, queryItem2, targetDistractorsBetween, drawFn, drawTwoFn) {
  const idx1 = ordering.indexOf(queryItem1);
  const idx2 = ordering.indexOf(queryItem2);
  if (idx1 === -1 || idx2 === -1) {
    throw new Error(`Query items not found in ordering: ${queryItem1} (${idx1}), ${queryItem2} (${idx2})`);
  }

  const idxHigher = Math.min(idx1, idx2);
  const idxLower = Math.max(idx1, idx2);

  const betweenGaps = [];
  for (let g = idxHigher; g < idxLower; g++) {
    betweenGaps.push(g);
  }

  const outsideGaps = [];
  outsideGaps.push(-1);
  outsideGaps.push(ordering.length - 1);
  for (let g = 0; g < ordering.length - 1; g++) {
    if (g < idxHigher || g >= idxLower) {
      outsideGaps.push(g);
    }
  }

  let assignedGaps;
  if (targetDistractorsBetween === 0) {
    const shuffled = shuffledCopy(outsideGaps);
    assignedGaps = [shuffled[0], shuffled[1]];
  } else if (targetDistractorsBetween === 1) {
    assignedGaps = [
      randomChoice(betweenGaps),
      randomChoice(outsideGaps),
    ];
  } else if (targetDistractorsBetween === 2) {
    if (betweenGaps.length >= 2) {
      const shuffled = shuffledCopy(betweenGaps);
      assignedGaps = [shuffled[0], shuffled[1]];
    } else {
      assignedGaps = [betweenGaps[0], betweenGaps[0]];
    }
  }

  // Bucket names by gap: -1 -> 'above-1', g -> 'between-(g+1)-(g+2)', N-1 -> 'below-N'.
  const n = ordering.length;
  const BUCKET_NAMES = ['above-1'];
  for (let i = 1; i < n; i++) BUCKET_NAMES.push(`between-${i}-${i + 1}`);
  BUCKET_NAMES.push(`below-${n}`);
  function bucketForGap(g) { return BUCKET_NAMES[g + 1]; }

  const distractorIds = [];
  const distractorRankBuckets = [];
  const excludeIds = new Set();

  if (assignedGaps[0] === assignedGaps[1]) {
    // Both in one gap: two distractors of that bucket, in their order within the bucket.
    const bucket = bucketForGap(assignedGaps[0]);
    const [d1, d2] = drawTwoFn(bucket, excludeIds);
    distractorIds.push(d1, d2);
    distractorRankBuckets.push(bucket, bucket);
  } else {
    for (const gap of assignedGaps) {
      const bucket = bucketForGap(gap);
      const d = drawFn(bucket, excludeIds);
      distractorIds.push(d);
      distractorRankBuckets.push(bucket);
      excludeIds.add(d);
    }
  }

  // Insert in descending gap order, so that no insertion shifts the place of a later one.
  const insertions = assignedGaps
    .map((gap, i) => ({ gap, distractor: distractorIds[i] }))
    .sort((a, b) => b.gap - a.gap);

  const chain = [...ordering];
  for (const { gap, distractor } of insertions) {
    chain.splice(gap + 1, 0, distractor);
  }

  const finalDistractorPositions = distractorIds.map(d => chain.indexOf(d));

  const links = [];
  for (let i = 0; i < chain.length - 1; i++) {
    links.push({ higher: chain[i], lower: chain[i + 1] });
  }

  return {
    chain,
    links,
    distractorPositions: finalDistractorPositions,
    distractorIds,
    distractorRankBuckets,
  };
}

/**
 * A chain with one distractor at each end: [endHigher, ...ordering, endLower] (the ICL test and
 * the practice blocks).
 *
 * @param {string[]} ordering - Item IDs, highest to lowest.
 * @param {string} endHigher - Distractor above the highest item.
 * @param {string} endLower - Distractor below the lowest item.
 * @returns {{chain: string[], links: Array<{higher: string, lower: string}>}}
 */
export function buildFixedEndChain(ordering, endHigher, endLower) {
  const chain = [endHigher, ...ordering, endLower];
  const links = [];
  for (let i = 0; i < chain.length - 1; i++) {
    links.push({ higher: chain[i], lower: chain[i + 1] });
  }
  return { chain, links };
}

/**
 * Assign the links of a chain to positions in the pair row, in random order. Pair index 0 is
 * the leftmost pair. Within each pair the higher-ranked item is shown on top.
 *
 * @param {Array<{higher: string, lower: string}>} links - Chain links.
 * @returns {Array<{pairIndex: number, topItem: string, bottomItem: string, topIsHigher: boolean,
 *   higher: string, lower: string}>}
 */
export function assignSlotsToLinks(links) {
  const pairOrder = shuffledIndices(links.length);
  return links.map((link, i) => ({
    pairIndex: pairOrder[i],
    topItem: link.higher,
    bottomItem: link.lower,
    topIsHigher: true,
    higher: link.higher,
    lower: link.lower,
  }));
}

/**
 * The number of links between two items in a chain.
 * @param {string} item1
 * @param {string} item2
 * @param {string[]} chain
 * @returns {number}
 */
export function computeContextHops(item1, item2, chain) {
  const idx1 = chain.indexOf(item1);
  const idx2 = chain.indexOf(item2);
  return Math.abs(idx1 - idx2);
}

// --- The context window (learning and practice) ---

/**
 * Phases whose chain is shown through a window: the learning trials and the first single-step
 * and multistep practice blocks. Their retry blocks, the tests and the masked trials show the
 * whole chain.
 */
export const WINDOWED_PHASES = new Set([
  'training',
  'practice_singlehop',
  'practice_multihop',
]);

/**
 * Show only a contiguous window of the chain: L pairs, L ~ Uniform(minContextPairs, all pairs).
 * The window keeps every link between the two queried items and, where the chain allows, one
 * more item above the higher and one below the lower queried item; the other items of the
 * window are split at random between the two ends. Mutates `params`: chain, links, slots (the
 * pair positions are drawn again), distractor fields, contextHops and numContextPairs.
 *
 * Phases outside WINDOWED_PHASES, and chains no longer than the minimum, are left whole;
 * numContextPairs is set in every case.
 *
 * @param {object} params - Trial parameters (mutated).
 * @param {number} minContextPairs - Smallest window, in pairs.
 * @returns {void}
 */
export function applyContextWindow(params, minContextPairs) {
  const fullPairs = params.chain.length - 1;
  if (!WINDOWED_PHASES.has(params.phase) || fullPairs <= minContextPairs) {
    params.numContextPairs = fullPairs;
    return;
  }

  const { chain, queryHigher, queryLower } = params;
  const iH = chain.indexOf(queryHigher);
  const iL = chain.indexOf(queryLower);
  if (iH < 0 || iL < 0 || iH > iL) {
    throw new Error(
      `[applyContextWindow] Query items not contiguous in chain: ` +
      `queryHigher=${queryHigher} (idx ${iH}), queryLower=${queryLower} (idx ${iL}).`
    );
  }

  const L = randomInt(minContextPairs, fullPairs);
  const connectingLen = iL - iH + 1;
  const extras = (L + 1) - connectingLen;
  const availableAbove = iH;
  const availableBelow = (chain.length - 1) - iL;

  const minAboveFraming = Math.min(1, availableAbove);
  const minBelowFraming = Math.min(1, availableBelow);

  const lo = Math.max(minAboveFraming, extras - availableBelow);
  const hi = Math.min(extras - minBelowFraming, availableAbove);
  if (lo > hi) {
    throw new Error(
      `[applyContextWindow] Infeasible window split: lo=${lo}, hi=${hi}, ` +
      `extras=${extras}, availableAbove=${availableAbove}, ` +
      `availableBelow=${availableBelow}, phase=${params.phase}.`
    );
  }
  const extraAbove = randomInt(lo, hi);
  const extraBelow = extras - extraAbove;

  const start = iH - extraAbove;
  const end = iL + extraBelow;
  const windowChain = chain.slice(start, end + 1);

  const newLinks = [];
  for (let i = 0; i < windowChain.length - 1; i++) {
    newLinks.push({ higher: windowChain[i], lower: windowChain[i + 1] });
  }

  const newSlots = assignSlotsToLinks(newLinks);

  const windowSet = new Set(windowChain);
  const newDistractorIds = [];
  const newDistractorPositions = [];
  const newDistractorRankBuckets = [];
  const oldIds = params.distractorIds || [];
  const oldBuckets = params.distractorRankBuckets || [];
  for (let i = 0; i < oldIds.length; i++) {
    const did = oldIds[i];
    if (windowSet.has(did)) {
      newDistractorIds.push(did);
      newDistractorPositions.push(windowChain.indexOf(did));
      newDistractorRankBuckets.push(oldBuckets[i]);
    }
  }

  params.chain = windowChain;
  params.links = newLinks;
  params.slots = newSlots;
  params.distractorIds = newDistractorIds;
  params.distractorPositions = newDistractorPositions;
  params.distractorRankBuckets = newDistractorRankBuckets;
  params.contextHops = computeContextHops(queryHigher, queryLower, windowChain);
  params.numContextPairs = L;
}

// --- Sequence constraints (learning and practice) ---

/**
 * Draws the number of distractors between the queried items (0, 1 or 2) from
 * CONFIG.distractorsBetweenDist. When a value would run longer than its limit in
 * CONFIG.maxDistractorsBetweenStreaks, it is drawn again from the other values.
 */
export const distractorsBetweenTracker = {
  _maxStreaks: { ...CONFIG.maxDistractorsBetweenStreaks },
  _values: Object.keys(CONFIG.distractorsBetweenDist).map(Number),
  _weights: Object.values(CONFIG.distractorsBetweenDist),
  /** Values drawn so far, most recent last. */
  _history: [],

  reset() {
    this._history = [];
  },

  /** @returns {number} 0, 1 or 2 */
  sample() {
    let value = this._weightedSample(this._values, this._weights);

    const limit = this._maxStreaks[value] ?? Infinity;
    if (this._history.length >= limit) {
      const recent = this._history.slice(-limit);
      if (recent.every(v => v === value)) {
        const others = [];
        const otherWeights = [];
        for (let i = 0; i < this._values.length; i++) {
          if (this._values[i] !== value) {
            others.push(this._values[i]);
            otherWeights.push(this._weights[i]);
          }
        }
        const wSum = otherWeights.reduce((a, b) => a + b, 0);
        value = this._weightedSample(others, otherWeights.map(w => w / wSum));
      }
    }

    this._history.push(value);
    return value;
  },

  _weightedSample(values, weights) {
    const r = Math.random();
    let cumulative = 0;
    for (let i = 0; i < values.length; i++) {
      cumulative += weights[i];
      if (r < cumulative) return values[i];
    }
    return values[values.length - 1];
  },
};

/**
 * The side of the correct answer, kept from running longer than CONFIG.maxCorrectSideStreak
 * trials on one side.
 */
export const querySideTracker = {
  maxStreak: CONFIG.maxCorrectSideStreak,
  /** Correct sides so far, most recent last. */
  _history: [],

  reset() {
    this._history = [];
  },

  /**
   * @param {string} side - 'left' or 'right'
   * @returns {boolean} True if `side` would make the run longer than maxStreak.
   */
  wouldViolate(side) {
    if (this._history.length < this.maxStreak) return false;
    const recent = this._history.slice(-this.maxStreak);
    return recent.every(s => s === side);
  },

  record(side) {
    this._history.push(side);
  },
};

/**
 * Put the two queried items on random sides; the side is flipped when it would run too long
 * (querySideTracker).
 *
 * @param {string} higher - The higher-ranked item.
 * @param {string} lower - The lower-ranked item.
 * @returns {{left: string, right: string, correctSide: 'left'|'right'}}
 */
export function randomizeQuerySides(higher, lower) {
  let side = Math.random() < 0.5 ? 'left' : 'right';

  if (querySideTracker.wouldViolate(side)) {
    side = side === 'left' ? 'right' : 'left';
  }

  querySideTracker.record(side);

  if (side === 'left') {
    return { left: higher, right: lower, correctSide: 'left' };
  }
  return { left: lower, right: higher, correctSide: 'right' };
}

/**
 * Draws the queried pair from a set of candidate pairs. When the last CONFIG.maxQueryPairStreak
 * trials all asked about one pair (in either order), that pair is left out of the draw.
 */
export const queryPairTracker = {
  maxStreak: CONFIG.maxQueryPairStreak,
  /** Pairs drawn so far, as order-free keys, most recent last. */
  _history: [],

  reset() {
    this._history = [];
  },

  _key(a, b) {
    return [a, b].slice().sort().join('|');
  },

  /**
   * @param {Array<[string,string]>} candidatePairs - [higher, lower] pairs.
   * @returns {[string,string]} The chosen [higher, lower].
   */
  sample(candidatePairs) {
    let pool = candidatePairs;
    if (this._history.length >= this.maxStreak) {
      const tail = this._history.slice(-this.maxStreak);
      const last = tail[0];
      if (tail.every(k => k === last)) {
        const filtered = candidatePairs.filter(([h, l]) => this._key(h, l) !== last);
        if (filtered.length > 0) pool = filtered;
      }
    }
    const [higher, lower] = randomChoice(pool);
    this._history.push(this._key(higher, lower));
    return [higher, lower];
  },
};

// --- Labels ---

/**
 * An image label as participants read it: underscores become spaces, and parenthetical notes
 * and trailing digits are removed. The labels of ALL_IMAGES have none of these, so they are
 * shown as they are.
 *
 * @param {string} label - Label from ALL_IMAGES.
 * @returns {string}
 */
export function formatLabel(label) {
  return label
    .replace(/_/g, ' ')
    .replace(/\s*\([^)]*\)/g, '')
    .replace(/\d+$/, '')
    .trim();
}
