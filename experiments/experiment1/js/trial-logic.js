/**
 * Trial parameters for the practice blocks, the learning phase and the three tests. No jsPsych
 * and no page: trials.js turns the parameters into timeline nodes.
 *
 * @module trial-logic
 */

import { CONFIG } from './config.js';
import {
  stimuliState, drawRankedDistractor, drawTwoRankedDistractors,
  getBucketForGap, RANK_BUCKET_NAMES,
} from './stimuli.js';
import {
  shuffleArray, shuffledCopy, randomChoice,
  buildAugmentedChain, buildFixedEndChain, assignSlotsToLinks,
  computeContextHops, randomizeQuerySides,
  generateDistanceUniformPairs, scheduleNoConsecutive, scheduleNoConsecutiveTwoKey,
  getPairsAtDistance, distractorsBetweenTracker, queryPairTracker,
  applyContextWindow,
} from './utils.js';

/**
 * The parameters of one trial.
 *
 * @typedef {object} TrialParams
 * @property {string} queryHigher - The queried item of higher rank.
 * @property {string} queryLower - The queried item of lower rank.
 * @property {number} queryHigherRank - Its rank in the ordering it is tested on (1 = top).
 * @property {number} queryLowerRank
 * @property {string} left - The item shown on the left.
 * @property {string} right - The item shown on the right.
 * @property {'left'|'right'} correctSide - The side of the higher-ranked item.
 * @property {?('left'|'right')} iclConsistentSide - ICL and arbitrage tests: the side the
 *   displayed chain points to.
 * @property {string[]} chain - The displayed items, from the top of the chain.
 * @property {Array<{higher: string, lower: string}>} links - Neighboring items of the chain.
 * @property {number[]} distractorPositions - Positions of the distractors in the chain.
 * @property {string[]} distractorIds - The distractors in the chain.
 * @property {string[]} distractorRankBuckets - Their rank buckets.
 * @property {object[]} slots - The pairs of the pair row (utils.assignSlotsToLinks).
 * @property {number} ordinalDistance - Symbolic distance between the queried items.
 * @property {?number} contextHops - Links between the queried items in the shown chain.
 * @property {string} phase - The saved phase value.
 * @property {string[]} ordering - The ordering the trial is built on.
 * @property {number} targetDistractorsBetween - Distractors drawn between the queried items.
 * @property {?string} swappedItemId - Learning: the main item replaced by a distractor.
 * @property {?string} swapDistractorId - The distractor shown in its place.
 * @property {?string} swapDistractorRankBucket - That distractor's rank bucket.
 * @property {string} contextDisplay - 'shown', 'masked' (gray boxes) or 'query_only' (no pair
 *   row).
 * @property {number} numContextPairs - Pairs shown.
 * @property {?number} iclOrderingId - ICL test: which of the novel orderings (0-4).
 */

// --- Trials with distractors inside the chain (learning and arbitrage) ---

/**
 * A trial on `ordering` with two distractors placed by rank bucket (utils.buildAugmentedChain;
 * buckets count from the top of `ordering` as displayed), then windowed (learning only). On
 * learning trials one main item outside the query is replaced by a distractor from the rank
 * bucket just below it.
 *
 * @param {object} params
 * @param {string} params.queryHigher - Higher-ranked queried item.
 * @param {string} params.queryLower - Lower-ranked queried item.
 * @param {string[]} params.ordering - Item IDs, top to bottom, as displayed.
 * @param {number} params.targetDistractorsBetween - 0, 1 or 2.
 * @param {string} params.phase - 'training' or 'test_arbitrage'.
 * @param {number} [params.queryHigherRank] - Rank to record when it is not the position in
 *   `ordering` (arbitrage shows the trained ordering reversed).
 * @param {number} [params.queryLowerRank]
 * @returns {TrialParams}
 */
export function computeTrialParams(params) {
  const {
    queryHigher, queryLower, ordering, targetDistractorsBetween, phase,
  } = params;

  const chainExcludeIds = new Set();

  const drawFn = (bucketName, excludeIds) =>
    drawRankedDistractor(bucketName, new Set([...chainExcludeIds, ...(excludeIds || [])]));
  const drawTwoFn = (bucketName, excludeIds) =>
    drawTwoRankedDistractors(bucketName, new Set([...chainExcludeIds, ...(excludeIds || [])]));

  const { chain, links, distractorPositions, distractorIds, distractorRankBuckets } =
    buildAugmentedChain(ordering, queryHigher, queryLower, targetDistractorsBetween, drawFn, drawTwoFn);

  const slots = assignSlotsToLinks(links);
  const { left, right, correctSide } = randomizeQuerySides(queryHigher, queryLower);
  const ordinalDistance = Math.abs(ordering.indexOf(queryHigher) - ordering.indexOf(queryLower));
  const contextHops = computeContextHops(queryHigher, queryLower, chain);

  const queryHigherRank = params.queryHigherRank ?? (ordering.indexOf(queryHigher) + 1);
  const queryLowerRank = params.queryLowerRank ?? (ordering.indexOf(queryLower) + 1);

  const tp = {
    queryHigher, queryLower, queryHigherRank, queryLowerRank,
    left, right, correctSide,
    iclConsistentSide: null,
    chain, links,
    distractorPositions, distractorIds, distractorRankBuckets,
    slots, ordinalDistance, contextHops,
    phase, ordering, targetDistractorsBetween,
    swappedItemId: null, swapDistractorId: null, swapDistractorRankBucket: null,
    contextDisplay: 'shown',
    numContextPairs: chain.length - 1,
    iclOrderingId: null,
  };

  applyContextWindow(tp, CONFIG.minContextPairs);

  // Learning trials: replace one shown main item outside the query by a distractor.
  if (phase === 'training') {
    const excludeIds = new Set([queryHigher, queryLower, ...tp.distractorIds]);
    const eligible = [];
    for (const slot of tp.slots) {
      if (!excludeIds.has(slot.topItem)) eligible.push({ slot, side: 'top' });
      if (!excludeIds.has(slot.bottomItem)) eligible.push({ slot, side: 'bottom' });
    }
    if (eligible.length > 0) {
      const pick = randomChoice(eligible);
      const itemToSwap = pick.side === 'top' ? pick.slot.topItem : pick.slot.bottomItem;

      // The distractor comes from the bucket just below the replaced item (for the lowest
      // item, the bottom bucket).
      const swapBucket = getBucketForGap(ordering.indexOf(itemToSwap));

      const allChainIds = new Set(tp.chain);
      allChainIds.delete(itemToSwap);
      const swapId = drawRankedDistractor(swapBucket, allChainIds);
      tp.swapDistractorId = swapId;
      tp.swapDistractorRankBucket = swapBucket;
      tp.swappedItemId = itemToSwap;
      if (pick.side === 'top') {
        pick.slot.topItem = swapId;
      } else {
        pick.slot.bottomItem = swapId;
      }
      // The chain records what was shown.
      const chainIdx = tp.chain.indexOf(itemToSwap);
      if (chainIdx !== -1) tp.chain[chainIdx] = swapId;
    }
  }

  if (phase === 'test_arbitrage') {
    const chainIdxHigher = tp.chain.indexOf(queryHigher);
    const chainIdxLower = tp.chain.indexOf(queryLower);
    const displayHigher = chainIdxHigher < chainIdxLower ? queryHigher : queryLower;
    tp.iclConsistentSide = displayHigher === left ? 'left' : 'right';
  }

  return tp;
}

// --- Learning ---

/**
 * A learning trial: an adjacent pair of the trained ordering, with the context shown.
 * @returns {TrialParams}
 */
export function generateOneTrainingTrialParams() {
  const ordering = stimuliState.trainedOrdering;
  const adjacentPairs = getPairsAtDistance(ordering, 1);
  const [higher, lower] = queryPairTracker.sample(adjacentPairs);
  const targetDistractorsBetween = distractorsBetweenTracker.sample();

  return computeTrialParams({
    queryHigher: higher,
    queryLower: lower,
    ordering,
    targetDistractorsBetween,
    phase: 'training',
  });
}

/**
 * A learning trial with the context masked, as in the IWL test: an adjacent pair of the
 * trained ordering, with feedback.
 * @returns {TrialParams}
 */
export function generateOneMaskedTrainingTrialParams() {
  const ordering = stimuliState.trainedOrdering;
  const adjacentPairs = getPairsAtDistance(ordering, 1);
  const [higher, lower] = queryPairTracker.sample(adjacentPairs);

  const { chain, links, slots, distractorIds, contextDisplay } =
    buildMaskedChainAndSlots(ordering);
  const { left, right, correctSide } = randomizeQuerySides(higher, lower);
  const ordinalDistance = Math.abs(ordering.indexOf(higher) - ordering.indexOf(lower));

  return {
    queryHigher: higher,
    queryLower: lower,
    queryHigherRank: ordering.indexOf(higher) + 1,
    queryLowerRank: ordering.indexOf(lower) + 1,
    left, right, correctSide,
    iclConsistentSide: null,
    chain,
    links,
    distractorPositions: [],
    distractorIds,
    distractorRankBuckets: [],
    slots,
    ordinalDistance,
    contextHops: null,
    phase: 'training',
    ordering,
    targetDistractorsBetween: 0,
    swappedItemId: null,
    swapDistractorId: null,
    swapDistractorRankBucket: null,
    contextDisplay,
    numContextPairs: chain.length - 1,
    iclOrderingId: null,
  };
}

// --- Tests ---

/**
 * A trial on [endHigher, ...ordering, endLower] (ICL test and practice), windowed in the first
 * single-step and multistep practice blocks (utils.applyContextWindow).
 *
 * @param {object} opts
 * @returns {TrialParams}
 */
function buildFixedChainTrial({ queryHigher, queryLower, ordering,
  phase, endHigher, endLower, queryHigherRank, queryLowerRank,
  iclOrderingId = null }) {
  const { chain, links } = buildFixedEndChain(ordering, endHigher, endLower);
  const slots = assignSlotsToLinks(links);
  const { left, right, correctSide } = randomizeQuerySides(queryHigher, queryLower);
  const ordinalDistance = Math.abs(ordering.indexOf(queryHigher) - ordering.indexOf(queryLower));
  const contextHops = computeContextHops(queryHigher, queryLower, chain);

  const finalHigherRank = queryHigherRank ?? (ordering.indexOf(queryHigher) + 1);
  const finalLowerRank = queryLowerRank ?? (ordering.indexOf(queryLower) + 1);

  const tp = {
    queryHigher, queryLower,
    queryHigherRank: finalHigherRank, queryLowerRank: finalLowerRank,
    left, right, correctSide,
    iclConsistentSide: null,
    chain, links, distractorPositions: [0, chain.length - 1],
    distractorIds: [endHigher, endLower],
    distractorRankBuckets: [RANK_BUCKET_NAMES[0], RANK_BUCKET_NAMES[RANK_BUCKET_NAMES.length - 1]],
    slots, ordinalDistance, contextHops,
    phase, ordering, targetDistractorsBetween: 0,
    swappedItemId: null, swapDistractorId: null, swapDistractorRankBucket: null,
    contextDisplay: 'shown',
    numContextPairs: chain.length - 1,
    iclOrderingId,
  };

  applyContextWindow(tp, CONFIG.minContextPairs);

  if (phase === 'test_icl') {
    const chainIdxHigher = tp.chain.indexOf(queryHigher);
    const chainIdxLower = tp.chain.indexOf(queryLower);
    const displayHigher = chainIdxHigher < chainIdxLower ? queryHigher : queryLower;
    tp.iclConsistentSide = displayHigher === left ? 'left' : 'right';
  }

  return tp;
}

/**
 * The rank pairs shared by the three tests, balanced over symbolic distance
 * (utils.generateDistanceUniformPairs). Drawn once per session.
 *
 * @returns {Array<{higherRank: number, lowerRank: number, distance: number, pairCategory: string}>}
 */
export function generateTestPairHistogram() {
  return generateDistanceUniformPairs(
    CONFIG.numItems,
    CONFIG.numTestTrialsPerType
  );
}

/**
 * The ICL test. Each trial shows one of the novel orderings, with its two end distractors.
 *
 * Each rank pair goes to as many different orderings as it has trials, so no ordering asks
 * about the same rank pair twice; pairs with more trials are placed first, each on the
 * orderings with the fewest trials so far (ties at random), so the orderings get equal numbers
 * of trials within one. The trials are then ordered so that neither the ordering nor the rank
 * pair repeats on consecutive trials.
 *
 * @param {Array<{higherRank, lowerRank, distance, pairCategory}>} rankPairs - From
 *   generateTestPairHistogram().
 * @returns {TrialParams[]}
 */
export function generateICLTestTrials(rankPairs) {
  const numOrderings = CONFIG.numICLOrderings;
  const orderings = stimuliState.iclOrderings;
  const endDistractors = stimuliState.iclEndDistractors;

  const byCategory = new Map();
  for (const p of rankPairs) {
    if (!byCategory.has(p.pairCategory)) byCategory.set(p.pairCategory, []);
    byCategory.get(p.pairCategory).push(p);
  }
  // Most trials first; ties are broken by random draws inside the comparator, so the number
  // of draws depends on the engine's sort algorithm. Node (V8, as in Chrome) reproduces every
  // session that was run.
  const sortedCategories = [...byCategory.keys()].sort((a, b) =>
    byCategory.get(b).length - byCategory.get(a).length ||
    (Math.random() - 0.5)
  );
  const orderingCounts = Array(numOrderings).fill(0);
  const taggedTrials = [];
  for (const category of sortedCategories) {
    const ps = byCategory.get(category);
    const kP = ps.length;
    if (kP > numOrderings) {
      throw new Error(
        `generateICLTestTrials: rank pair ${category} has ${kP} trials ` +
        `but there are only ${numOrderings} orderings.`
      );
    }
    const indexed = orderingCounts.map((c, i) => ({ c, i, jitter: Math.random() }));
    indexed.sort((a, b) => a.c - b.c || a.jitter - b.jitter);
    const chosen = indexed.slice(0, kP).map(x => x.i);
    for (let n = 0; n < kP; n++) {
      const orderingId = chosen[n];
      taggedTrials.push({ ...ps[n], orderingId });
      orderingCounts[orderingId] += 1;
    }
  }

  const scheduled = scheduleNoConsecutiveTwoKey(
    taggedTrials,
    t => `O${t.orderingId}`,
    t => t.pairCategory,
  );

  const allTrials = scheduled.map(t => {
    const ordering = orderings[t.orderingId].map(s => s.id);
    const endPair = endDistractors[t.orderingId];
    const endHigher = endPair[0].id;
    const endLower = endPair[1].id;
    return buildFixedChainTrial({
      queryHigher: ordering[t.higherRank - 1],
      queryLower:  ordering[t.lowerRank  - 1],
      ordering,
      phase: 'test_icl',
      endHigher,
      endLower,
      queryHigherRank: t.higherRank,
      queryLowerRank: t.lowerRank,
      iclOrderingId: t.orderingId,
    });
  });
  return allTrials;
}

/**
 * The masked context of the IWL test and of the masked learning trials: the trained items and
 * two learning distractors in a new random order on every trial, each pair image shown as a
 * gray box. The arrows keep their orientation; the boxes carry no identity.
 *
 * @param {string[]} ordering - The trained ordering.
 * @returns {{chain: string[], links: object[], slots: object[], distractorIds: string[],
 *   contextDisplay: string}}
 */
function buildMaskedChainAndSlots(ordering) {
  const allDistractorIds = stimuliState.trainingDistractors.map(s => s.id);
  const twoDistractors = shuffledCopy(allDistractorIds).slice(0, CONFIG.numDistractorsPerTrial);
  const chain = shuffledCopy([...ordering, ...twoDistractors]);
  const links = [];
  for (let i = 0; i < chain.length - 1; i++) {
    links.push({ higher: chain[i], lower: chain[i + 1] });
  }
  const slots = assignSlotsToLinks(links);
  for (const slot of slots) {
    slot.maskItem = true;
  }
  return { chain, links, slots, distractorIds: twoDistractors, contextDisplay: 'masked' };
}

/** The test's query pairs: each rank pair as items of the trained ordering. */
function queryPairsOf(rankPairs, ordering) {
  return rankPairs.map(p => ({
    higher: ordering[p.higherRank - 1],
    lower:  ordering[p.lowerRank  - 1],
    higherRank: p.higherRank,
    lowerRank:  p.lowerRank,
    distance:   p.distance,
    pairCategory: p.pairCategory,
  }));
}

/**
 * The IWL test: pairs of the trained ordering with the context masked, shuffled, then ordered
 * so that no rank pair repeats on consecutive trials.
 *
 * @param {Array<object>} rankPairs - From generateTestPairHistogram().
 * @returns {TrialParams[]}
 */
export function generateIWLTestTrials(rankPairs) {
  const ordering = stimuliState.trainedOrdering;
  const allTrials = queryPairsOf(rankPairs, ordering).map(pair => {
    const { chain, links, slots, distractorIds, contextDisplay } =
      buildMaskedChainAndSlots(ordering);
    const { left, right, correctSide } = randomizeQuerySides(pair.higher, pair.lower);

    return {
      queryHigher: pair.higher,
      queryLower: pair.lower,
      queryHigherRank: pair.higherRank,
      queryLowerRank: pair.lowerRank,
      left, right, correctSide,
      iclConsistentSide: null,
      chain,
      links,
      distractorPositions: [],
      distractorIds,
      distractorRankBuckets: [],
      slots,
      ordinalDistance: pair.distance,
      contextHops: null,
      phase: 'test_iwl',
      ordering,
      targetDistractorsBetween: 0,
      swappedItemId: null,
      swapDistractorId: null,
      swapDistractorRankBucket: null,
      contextDisplay,
      numContextPairs: chain.length - 1,
      iclOrderingId: null,
    };
  });
  return scheduleNoConsecutive(
    shuffleArray(allTrials), t => `${t.queryHigherRank}_${t.queryLowerRank}`
  );
}

/**
 * The arbitrage test: pairs of the trained items shown in a chain that reverses the trained
 * ordering, with two distractors outside the queried pair, placed by rank bucket counted from
 * the top of the reversed chain. The correct answer follows the trained ordering, against the
 * display. Ordered so that no rank pair repeats on consecutive trials.
 *
 * @param {Array<object>} rankPairs - From generateTestPairHistogram().
 * @returns {TrialParams[]}
 */
export function generateArbitrageTestTrials(rankPairs) {
  const ordering = stimuliState.trainedOrdering;
  const allTrials = queryPairsOf(rankPairs, ordering).map(pair => {
    const reversedOrdering = [...ordering].reverse();
    return computeTrialParams({
      queryHigher: pair.higher,
      queryLower: pair.lower,
      ordering: reversedOrdering,
      targetDistractorsBetween: 0,
      phase: 'test_arbitrage',
      queryHigherRank: pair.higherRank,
      queryLowerRank: pair.lowerRank,
    });
  });
  return scheduleNoConsecutive(
    allTrials,
    t => `${t.queryHigherRank}_${t.queryLowerRank}`
  );
}

// --- Practice ---

/**
 * A query-only practice trial (block 1): an adjacent pair of the query-only practice items,
 * shown without a pair row.
 *
 * @param {string[]} ordering - The query-only practice ordering.
 * @param {string} [phase='practice_query']
 * @returns {TrialParams}
 */
export function generateOneQueryOnlyPracticeTrialParams(ordering, phase = 'practice_query') {
  const available = getPairsAtDistance(ordering, 1);
  const [higher, lower] = queryPairTracker.sample(available);
  const { left, right, correctSide } = randomizeQuerySides(higher, lower);
  const ordinalDistance = Math.abs(ordering.indexOf(higher) - ordering.indexOf(lower));
  const queryHigherRank = ordering.indexOf(higher) + 1;
  const queryLowerRank = ordering.indexOf(lower) + 1;

  return {
    queryHigher: higher,
    queryLower: lower,
    queryHigherRank,
    queryLowerRank,
    left, right, correctSide,
    iclConsistentSide: null,
    chain: [],
    links: [],
    distractorPositions: [],
    distractorIds: [],
    distractorRankBuckets: [],
    slots: [],
    ordinalDistance,
    contextHops: null,
    phase,
    ordering,
    targetDistractorsBetween: 0,
    swappedItemId: null,
    swapDistractorId: null,
    swapDistractorRankBucket: null,
    contextDisplay: 'query_only',
    numContextPairs: 0,
    iclOrderingId: null,
  };
}

/**
 * A single-step practice trial (block 2): an adjacent pair of the practice ordering.
 *
 * @param {string[]} ordering - The practice ordering.
 * @param {string} [phase='practice_singlehop']
 * @returns {TrialParams}
 */
export function generateOneAdjacentPracticeTrialParams(ordering, phase = 'practice_singlehop') {
  const available = getPairsAtDistance(ordering, 1);
  const [higher, lower] = queryPairTracker.sample(available);
  const endHigher = stimuliState.practiceEndDistractors[0].id;
  const endLower = stimuliState.practiceEndDistractors[1].id;

  return buildFixedChainTrial({
    queryHigher: higher,
    queryLower: lower,
    ordering,
    phase,
    endHigher,
    endLower,
  });
}

/**
 * A multistep practice trial (block 3): a pair of the practice ordering at symbolic distance
 * 2 or 3.
 *
 * @param {string[]} ordering - The practice ordering.
 * @param {string} [phase='practice_multihop']
 * @returns {TrialParams}
 */
export function generateOneMultiHopPracticeTrialParams(ordering, phase = 'practice_multihop') {
  const distance = randomChoice([2, 3]);
  const available = getPairsAtDistance(ordering, distance);
  const [higher, lower] = queryPairTracker.sample(available);
  const endHigher = stimuliState.practiceEndDistractors[0].id;
  const endLower = stimuliState.practiceEndDistractors[1].id;

  return buildFixedChainTrial({
    queryHigher: higher,
    queryLower: lower,
    ordering,
    phase,
    endHigher,
    endLower,
  });
}
