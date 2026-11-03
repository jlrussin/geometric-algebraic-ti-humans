// The trial plan of Experiment 1, checked through the replay, and the design constants that the
// code sets.
//
//   node --test experiments/experiment1/tests/*.test.js
//
// Each session is rebuilt by replay.mjs in a process of its own (the experiment's modules keep
// their state), which prints its planned rows and the session's stimuli. Expected values come
// from the configuration (js/config.js) wherever it sets them.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { CONFIG, framesToMs } from '../js/config.js';
import { hashString, installSeededRandom } from '../js/seeded-rng.js';
import { ALL_IMAGES, RANK_BUCKET_NAMES, initStimuliState } from '../js/stimuli.js';
import { formatLabel } from '../js/utils.js';

const EXPERIMENT = dirname(dirname(fileURLToPath(import.meta.url)));
const ASSIGNMENTS = JSON.parse(readFileSync(join(EXPERIMENT, 'data', 'assignments.json'), 'utf8'))
  .assignments;

// Two assignments of each test order.
const SESSIONS = [0, 3, 1, 2];

/** Rebuild one session: its planned rows and its stimuli (as saved in the session record). */
function session(assignmentId) {
  const replayUrl = pathToFileURL(join(EXPERIMENT, 'replay.mjs')).href;
  const stimuliUrl = pathToFileURL(join(EXPERIMENT, 'js', 'stimuli.js')).href;
  const script = `
    import { replay } from ${JSON.stringify(replayUrl)};
    const { rows } = await replay({ assignmentId: ${assignmentId} });
    const { getStimuliSnapshot } = await import(${JSON.stringify(stimuliUrl)});
    const out = JSON.stringify({ rows, stimuli: getStimuliSnapshot() });
    process.stdout.write(out, () => process.exit(0));`;
  const text = execFileSync(process.execPath, ['--input-type=module', '-e', script],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const { rows, stimuli } = JSON.parse(text);
  return { rows, stimuli, trained: JSON.parse(stimuli.trained_ordering_json) };
}

const cache = new Map();
const get = (id) => {
  if (!cache.has(id)) cache.set(id, session(id));
  return cache.get(id);
};

const byPhase = (rows, phase) => rows.filter((r) => r.phase === phase);
const pairKey = (r) => `${Math.min(r.query_left_rank, r.query_right_rank)}_`
  + `${Math.max(r.query_left_rank, r.query_right_rank)}`;
const higherSide = (r) => (r.query_left_rank < r.query_right_rank ? 'left' : 'right');
/** Runs of equal values, as [value, length]. */
const runs = (values) => {
  const out = [];
  for (const v of values) {
    if (out.length && out.at(-1)[0] === v) out.at(-1)[1] += 1;
    else out.push([v, 1]);
  }
  return out;
};
const longestRun = (values) => Math.max(...runs(values).map(([, n]) => n));
const TESTS = { icl: 'test_icl', iwl: 'test_iwl', arbitrage: 'test_arbitrage' };

for (const id of SESSIONS) {
  const order = ASSIGNMENTS[id].test_block_order;

  test(`assignment ${id}: phases, counts and order`, () => {
    const { rows } = get(id);
    const expected = [
      ['practice_query', CONFIG.numQueryOnlyPracticeTrials],
      ['practice_query_extra', CONFIG.numQueryOnlyPracticeRetryTrials],
      ['practice_singlehop', CONFIG.numSinglehopPracticeTrials],
      ['practice_singlehop_extra', CONFIG.numExtraPracticeTrials],
      ['practice_multihop', CONFIG.numMultiHopPracticeTrials],
      ['practice_multihop_extra', CONFIG.numExtraPracticeTrials],
      ['training', CONFIG.numTrainingTrials],
      ...order.map((t) => [TESTS[t], CONFIG.numTestTrialsPerType]),
    ];
    const blocks = [];
    for (const r of rows) {
      if (blocks.length && blocks.at(-1)[0] === r.phase) blocks.at(-1)[1] += 1;
      else blocks.push([r.phase, 1]);
    }
    assert.deepEqual(blocks, expected);
  });

  test(`assignment ${id}: the stimuli use every image once`, () => {
    const { stimuli, trained } = get(id);
    const roles = stimuli.image_roles;
    const all = [
      ...roles.main_items, ...roles.training_distractors,
      ...Object.values(roles.icl_orderings).flat(),
      ...Object.values(roles.icl_end_distractors_per_ordering).flat(),
      ...roles.practice, ...roles.practice_end_distractors, ...roles.query_only_practice,
    ];
    assert.equal(all.length, ALL_IMAGES.length);
    assert.equal(new Set(all).size, ALL_IMAGES.length);
    assert.deepEqual([...trained].sort(), [...roles.main_items].sort());
    const buckets = stimuli.training_distractor_buckets[0];
    assert.deepEqual(Object.keys(buckets), RANK_BUCKET_NAMES);
    for (const ids of Object.values(buckets)) {
      assert.equal(ids.length, CONFIG.distractorsPerRankBucket);
    }
  });

  test(`assignment ${id}: practice`, () => {
    const { rows, stimuli } = get(id);
    const roles = stimuli.image_roles;
    for (const r of rows.filter((x) => x.phase.startsWith('practice_query'))) {
      assert.equal(r.context_display, 'query_only');
      assert.equal(r.num_context_pairs, 0);
      assert.equal(r.ordinal_distance, 1);
      assert.ok(roles.query_only_practice.includes(r.query_left));
    }
    for (const r of rows.filter((x) => /^practice_(single|multi)/.test(x.phase))) {
      const distances = r.phase.startsWith('practice_singlehop') ? [1] : [2, 3];
      assert.ok(distances.includes(r.ordinal_distance));
      assert.ok(roles.practice.includes(r.query_left) && roles.practice.includes(r.query_right));
      assert.equal(r.context_hops, r.ordinal_distance);
      assert.ok(r.num_context_pairs >= CONFIG.minContextPairs);
    }
  });

  test(`assignment ${id}: learning phase`, () => {
    const { rows, trained, stimuli } = get(id);
    const learning = byPhase(rows, 'training');
    const fullPairs = CONFIG.numItems - 1 + CONFIG.numDistractorsPerTrial;
    for (const r of learning) {
      assert.equal(r.ordinal_distance, 1);
      assert.equal(r.query_left_rank, trained.indexOf(r.query_left) + 1);
      assert.equal(r.query_right_rank, trained.indexOf(r.query_right) + 1);
    }
    const masked = learning.filter((r) => r.context_display === 'masked');
    const shown = learning.filter((r) => r.context_display === 'shown');
    assert.equal(masked.length,
      Math.round(CONFIG.numTrainingTrials * CONFIG.iwlDisplayProportionTraining));
    assert.equal(masked.length + shown.length, learning.length);
    for (const r of masked) {
      assert.equal(r.num_context_pairs, fullPairs);
      assert.equal(r.context_hops, null);
    }
    // Shown context: a window of 5 to 8 pairs, 0-2 intervening distractors, one main item
    // replaced by a distractor.
    const between = shown.map((r) => r.context_hops - r.ordinal_distance);
    assert.deepEqual([...new Set(between)].sort(), [0, 1, 2]);
    for (const [v, n] of runs(between)) assert.ok(n <= CONFIG.maxDistractorsBetweenStreaks[v]);
    const distractors = new Set(stimuli.image_roles.training_distractors);
    for (const r of shown) {
      assert.ok(r.num_context_pairs >= CONFIG.minContextPairs && r.num_context_pairs <= fullPairs);
      assert.ok(trained.includes(r.swapped_item_id));
      assert.ok(![r.query_left, r.query_right].includes(r.swapped_item_id));
      assert.ok(distractors.has(r.swap_distractor_id));
    }
    assert.ok(longestRun(learning.map(pairKey)) <= CONFIG.maxQueryPairStreak);
    assert.ok(longestRun(learning.map(higherSide)) <= CONFIG.maxCorrectSideStreak);
  });

  test(`assignment ${id}: the three tests ask about the same balanced rank pairs`, () => {
    const { rows } = get(id);
    const sets = order.map((t) => byPhase(rows, TESTS[t]).map(pairKey).sort());
    assert.deepEqual(sets[1], sets[0]);
    assert.deepEqual(sets[2], sets[0]);
    const counts = new Map();
    for (const k of sets[0]) counts.set(k, (counts.get(k) ?? 0) + 1);
    const n = CONFIG.numItems;
    assert.equal(counts.size, (n * (n - 1)) / 2);
    assert.ok(Math.max(...counts.values()) <= CONFIG.numICLOrderings);
    const perDistance = new Map();
    for (const r of byPhase(rows, 'test_icl')) {
      perDistance.set(r.ordinal_distance, (perDistance.get(r.ordinal_distance) ?? 0) + 1);
    }
    assert.deepEqual([...perDistance.keys()].sort(), [1, 2, 3, 4, 5, 6]);
    // Every rank pair once, and the remaining trials spread evenly over the distances.
    const extras = [...perDistance].map(([d, count]) => count - (n - d));
    assert.equal(extras.reduce((a, b) => a + b, 0), CONFIG.numTestTrialsPerType - counts.size);
    assert.ok(Math.max(...extras) - Math.min(...extras) <= 1);
    for (const t of order) {
      const block = byPhase(rows, TESTS[t]);
      for (let i = 1; i < block.length; i++) assert.notEqual(pairKey(block[i]), pairKey(block[i - 1]));
    }
  });

  test(`assignment ${id}: ICL test`, () => {
    const { rows, stimuli } = get(id);
    const orderings = stimuli.image_roles.icl_orderings;
    const ends = stimuli.image_roles.icl_end_distractors_per_ordering;
    const icl = byPhase(rows, 'test_icl');
    const perOrdering = new Map();
    const seen = new Set();
    icl.forEach((r, i) => {
      const ordering = orderings[r.icl_ordering];
      assert.deepEqual(JSON.parse(r.chain_order_json), [ends[r.icl_ordering][0], ...ordering,
        ends[r.icl_ordering][1]]);
      assert.equal(r.query_left_rank, ordering.indexOf(r.query_left) + 1);
      assert.equal(r.context_hops, r.ordinal_distance);
      assert.equal(r.icl_consistent_side, higherSide(r));
      assert.equal(r.num_context_pairs, CONFIG.numItems + 1);
      if (i > 0) assert.notEqual(r.icl_ordering, icl[i - 1].icl_ordering);
      const key = `${r.icl_ordering}:${pairKey(r)}`;
      assert.ok(!seen.has(key));
      seen.add(key);
      perOrdering.set(r.icl_ordering, (perOrdering.get(r.icl_ordering) ?? 0) + 1);
    });
    assert.equal(perOrdering.size, CONFIG.numICLOrderings);
    assert.ok(Math.max(...perOrdering.values()) - Math.min(...perOrdering.values()) <= 1);
  });

  test(`assignment ${id}: IWL and arbitrage tests`, () => {
    const { rows, trained } = get(id);
    for (const r of byPhase(rows, 'test_iwl')) {
      assert.equal(r.context_display, 'masked');
      assert.equal(r.query_left_rank, trained.indexOf(r.query_left) + 1);
      const chain = JSON.parse(r.chain_order_json);
      assert.equal(chain.length, CONFIG.numItems + CONFIG.numDistractorsPerTrial);
      assert.ok(trained.every((item) => chain.includes(item)));
    }
    const reversed = [...trained].reverse();
    for (const r of byPhase(rows, 'test_arbitrage')) {
      assert.equal(r.context_display, 'shown');
      assert.equal(r.query_left_rank, trained.indexOf(r.query_left) + 1);
      assert.equal(r.context_hops, r.ordinal_distance);
      assert.notEqual(r.icl_consistent_side, higherSide(r));
      const shownMain = JSON.parse(r.chain_order_json).filter((x) => trained.includes(x));
      assert.deepEqual(shownMain, reversed);
    }
  });
}

test('replays are deterministic', () => {
  const again = session(SESSIONS[0]);
  assert.deepEqual(again.rows, get(SESSIONS[0]).rows);
});

test('the stimuli assignment discards the 54 draws of the sessions in the data', () => {
  // Draws made by initStimuliState itself, not by the helpers it calls, are the discarded ones
  // (js/stimuli.js). Every later draw of a session depends on their number.
  const native = Math.random;
  try {
    installSeededRandom(hashString(String(SESSIONS[0])));
    const seeded = Math.random;
    let discarded = 0;
    Math.random = () => {
      if (/^\s*at initStimuliState\b/.test(new Error().stack.split('\n')[2] ?? '')) discarded += 1;
      return seeded();
    };
    initStimuliState();
    assert.equal(discarded, 17 + 6 + 16 + 15);
  } finally {
    Math.random = native;
  }
});

// --- Design constants reported in the paper -------------------------------------------------

test('items, images and roles', () => {
  assert.equal(CONFIG.numItems, 7);
  assert.equal(ALL_IMAGES.length, 80);
  const digested = readFileSync(join(EXPERIMENT, 'media.sha256'), 'utf8').trim().split('\n')
    .map((line) => line.split(/\s+/)[1]).sort();
  assert.deepEqual(ALL_IMAGES.map((s) => s.image).sort(), digested);
  assert.ok(ALL_IMAGES.every((s) => formatLabel(s.label).length <= 10));
  assert.equal(CONFIG.numDistractorsPerTrial, 2);
  assert.equal(CONFIG.numRankBuckets * CONFIG.distractorsPerRankBucket, 16);
  assert.equal(CONFIG.numICLOrderings, 5);
  assert.equal(CONFIG.numICLEndDistractors, 2);
  assert.equal(CONFIG.numICLOrderings * (CONFIG.numItems + CONFIG.numICLEndDistractors), 45);
  assert.equal(CONFIG.numItems + CONFIG.numPracticeEndDistractors
    + CONFIG.numQueryOnlyPracticeItems, 12);
});

test('learning phase and tests', () => {
  assert.equal(CONFIG.numTrainingTrials, 100);
  assert.equal(CONFIG.trainingBreakFrequency, 20);
  assert.equal(CONFIG.iwlDisplayProportionTraining, 0.1);
  assert.deepEqual(CONFIG.distractorsBetweenDist, { 0: 0.1, 1: 0.45, 2: 0.45 });
  assert.deepEqual(CONFIG.maxDistractorsBetweenStreaks, { 0: 3, 1: 3, 2: 3 });
  assert.equal(CONFIG.maxQueryPairStreak, 2);
  assert.equal(CONFIG.minContextPairs, 5);
  assert.equal(CONFIG.numItems - 1 + CONFIG.numDistractorsPerTrial, 8);
  assert.equal(CONFIG.numTestTrialsPerType, 40);
  const n = CONFIG.numItems;
  assert.equal((n * (n - 1)) / 2, 21);
  assert.equal(CONFIG.numTestTrialsPerType - (n * (n - 1)) / 2, 19);
  assert.ok(ASSIGNMENTS.every((r) => r.test_block_order.length === 3
    && r.test_block_order[2] === 'arbitrage'));
});

test('timing and responses', () => {
  assert.equal(CONFIG.responseDeadlineMs, 60000);
  assert.equal(CONFIG.testResponseDeadlineMs, 60000);
  assert.equal(framesToMs(CONFIG.timing.fixationFrames), 500);
  assert.equal(framesToMs(CONFIG.timing.feedbackCorrectFrames), 500);
  assert.equal(framesToMs(CONFIG.timing.feedbackIncorrectFrames), 5000);
  assert.equal(framesToMs(CONFIG.timing.feedbackNeutralFrames), 1000);
  assert.deepEqual(CONFIG.responseKeys, { left: 'f', right: 'j' });
});

test('instructions, practice and comprehension checks', async () => {
  globalThis.jsPsychHtmlKeyboardResponse = {};
  globalThis.jsPsychSurvey = {};
  const { initStimuliState } = await import('../js/stimuli.js');
  const { resolveBlockQuestions } = await import('../js/comprehension-questions.js');
  const { buildQuestionnaireTrials } = await import('../js/questionnaire.js');
  initStimuliState();
  for (const block of ['query', 'singlehop', 'multihop', 'final']) {
    assert.equal(resolveBlockQuestions(block).length, 4);
  }
  assert.equal(CONFIG.comprehensionMaxRetries + 1, 2);
  assert.equal(CONFIG.instructionMinViewMs, 5000);
  assert.equal(CONFIG.numQueryOnlyPracticeTrials, 10);
  assert.equal(CONFIG.numSinglehopPracticeTrials, 5);
  assert.equal(CONFIG.numMultiHopPracticeTrials, 5);
  assert.equal(CONFIG.practiceAccuracyThreshold, 0.7);
  assert.equal(CONFIG.practiceMaxRetries, 2);
  assert.equal(CONFIG.numExtraPracticeTrials, 5);
  assert.equal(CONFIG.numQueryOnlyPracticeRetryTrials, 5);
  const questionnaire = buildQuestionnaireTrials();
  assert.equal(questionnaire.filter((node) => node.data.phase === 'questionnaire').length, 10);
});

test('consent and page', () => {
  const consent = readFileSync(join(EXPERIMENT, 'js', 'consent.js'), 'utf8');
  assert.ok(consent.includes('between the ages of 18 and 65'));
  assert.ok(consent.includes('this will not exceed $5'));
  const page = readFileSync(join(EXPERIMENT, 'index.html'), 'utf8');
  assert.ok(page.includes('https://unpkg.com/jspsych@8.2.3"'));
});
