/**
 * jsPsych timeline nodes: the practice blocks, the learning phase, the tests, the comprehension
 * checks, breaks, the progress bar and the points counter. The trial parameters come from
 * trial-logic.js.
 *
 * @module trials
 */

import { CONFIG } from './config.js';
import { stimuliState } from './stimuli.js';
import { shuffledCopy, shuffledIndices } from './utils.js';
import {
  generateOneTrainingTrialParams,
  generateOneMaskedTrainingTrialParams,
  generateICLTestTrials,
  generateIWLTestTrials,
  generateArbitrageTestTrials,
  generateOneQueryOnlyPracticeTrialParams,
  generateOneAdjacentPracticeTrialParams,
  generateOneMultiHopPracticeTrialParams,
} from './trial-logic.js';
import { resolveBlockQuestions } from './comprehension-questions.js';
import { COMPREHENSION_FAILED_HTML } from './consent.js';
import { helpReminderHTML } from './instructions.js';

// --- Comprehension checks, practice attempts and the end of a failed session ---

export const comprehensionState = {
  /** Attempts so far per check, counted when an attempt starts. */
  attempts: { query: 0, singlehop: 0, multihop: 0, final: 0 },
  /**
   * Set after a failed attempt: the block's instruction pages count as unvisited again, so their
   * minimum viewing time applies again.
   */
  needsReset: { query: false, singlehop: false, multihop: false, final: false },
};

export const practiceState = {
  /** Practice blocks run per practice phase (1 + retry blocks). */
  attempts: { query: 0, singlehop: 0, multihop: 0 },
};

/**
 * Set when a comprehension check is failed on the last attempt; the session ends. `check` names
 * that check (`comprehension_<blockId>_exhausted`).
 */
export const failureState = {
  failed: false,
  check: null,
};

/**
 * Nodes that run only while no comprehension check has been failed on its last attempt.
 * @param {Array} nodes
 * @returns {object}
 */
export function unlessFailed(nodes) {
  return {
    timeline: nodes,
    conditional_function: () => !failureState.failed,
  };
}

/**
 * Nodes that run only after a comprehension check was failed on its last attempt.
 * @param {Array} nodes
 * @returns {object}
 */
export function ifFailed(nodes) {
  return {
    timeline: nodes,
    conditional_function: () => failureState.failed,
  };
}

// --- Progress bar ---

let phaseProgressEl = null;
let phaseProgressFill = null;

/**
 * Show a progress bar at the top of the screen for the learning phase or the test phase.
 * @param {string} label - "Learning phase" or "Test phase".
 */
export function showPhaseProgress(label) {
  removePhaseProgress();
  const container = document.createElement('div');
  container.className = 'phase-progress-container';
  container.innerHTML = `
    <div class="phase-progress-label">${label}</div>
    <div class="phase-progress-track">
      <div class="phase-progress-fill" style="width: 0%"></div>
    </div>`;
  document.body.appendChild(container);
  phaseProgressEl = container;
  phaseProgressFill = container.querySelector('.phase-progress-fill');
}

/**
 * @param {number} completed - Trials completed so far.
 * @param {number} total - Trials in the phase.
 */
export function updatePhaseProgress(completed, total) {
  if (!phaseProgressFill) return;
  const pct = Math.min(100, Math.round((completed / total) * 100));
  phaseProgressFill.style.width = `${pct}%`;
}

export function removePhaseProgress() {
  if (phaseProgressEl) {
    phaseProgressEl.remove();
    phaseProgressEl = null;
    phaseProgressFill = null;
  }
}

// --- Points ---
// One point per correct answer (and per arbitrage trial). A counter in the top-right corner
// shows the learning points; test points are counted without being shown.

let trainingPoints = 0;
let testPoints = 0;
let perfTrackerEl = null;

export function showPerformanceTracker() {
  trainingPoints = 0;
  removePerformanceTracker();
  const el = document.createElement('div');
  el.className = 'perf-tracker';
  el.innerHTML = '<span class="perf-tracker-icon">⭐</span> <span id="perf-tracker-count">0</span> pts';
  document.body.appendChild(el);
  perfTrackerEl = el;
}

/**
 * Called when the feedback of a learning trial appears.
 * @param {boolean} correct
 */
export function updatePerformanceTracker(correct) {
  if (correct) {
    trainingPoints++;
    const countEl = document.getElementById('perf-tracker-count');
    if (countEl) countEl.textContent = trainingPoints;
    if (perfTrackerEl) {
      perfTrackerEl.classList.remove('pulse');
      // Reading offsetWidth forces a reflow, so the pulse animation starts again.
      void perfTrackerEl.offsetWidth;
      perfTrackerEl.classList.add('pulse');
      const plus = document.createElement('span');
      plus.className = 'perf-plus-one';
      plus.textContent = '+1';
      perfTrackerEl.appendChild(plus);
      plus.addEventListener('animationend', () => plus.remove(), { once: true });
    }
  }
}

export function removePerformanceTracker() {
  if (perfTrackerEl) {
    perfTrackerEl.remove();
    perfTrackerEl = null;
  }
}

/** @param {boolean} correct */
export function recordTestPoint(correct) {
  if (correct) testPoints++;
}

/** @returns {{ training: number, test: number, total: number }} */
export function getPerformancePoints() {
  return { training: trainingPoints, test: testPoints, total: trainingPoints + testPoints };
}

// --- Breaks ---

/**
 * A break screen.
 *
 * @param {number} completed - Trials completed in the phase.
 * @param {number} total - Trials in the phase.
 * @param {string} phaseName - e.g. 'the learning phase'.
 * @param {boolean} showPoints - Show the points so far (learning breaks).
 * @param {?string} helpContext - 'training' or 'test': the help panel's content on the break.
 * @returns {object} jsPsych timeline node.
 */
export function buildBreakNode(completed, total, phaseName, showPoints, helpContext) {
  const pct = Math.round((completed / total) * 100);
  const pointsPlaceholder = showPoints
    ? '<p><span id="break-points-display"></span></p>' : '';
  const bonusReminder =
    '<p class="break-bonus-reminder">Remember: your performance determines your <strong>bonus payment</strong> — keep it up!</p>';
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="break-screen">
        <div class="break-progress">
          You've completed ${completed} of ${total} trials in ${phaseName}.
        </div>
        <div class="break-progress-bar">
          <div class="break-progress-fill" style="width: ${pct}%;"></div>
        </div>
        ${pointsPlaceholder}
        ${bonusReminder}
        <p>Take a short break if you need one.</p>
        ${helpReminderHTML()}
        <p>Press <kbd>Space</kbd> when you're ready to continue.</p>
      </div>
    `,
    choices: [' '],
    data: { phase: 'break', help_context: helpContext },
    on_load: () => {
      if (phaseProgressEl) phaseProgressEl.style.display = 'none';
      const pointsEl = document.getElementById('break-points-display');
      if (pointsEl) {
        pointsEl.textContent = `You've earned ${trainingPoints} points so far.`;
      }
    },
    on_finish: () => { if (phaseProgressEl) phaseProgressEl.style.display = ''; },
  };
}

// --- Task trials ---

/**
 * The timeline node of a task trial (display.js, LinkedListDisplayPlugin).
 *
 * @param {import('./trial-logic.js').TrialParams} tp
 * @param {number} responseDeadline - ms.
 * @param {boolean} showFeedback - Correct/incorrect feedback (practice and learning).
 * @param {boolean} [showNeutralFeedback=false] - Feedback that only shows the choice (tests).
 * @returns {object} jsPsych timeline node.
 */
function trialParamsToJsPsychNode(tp, responseDeadline, showFeedback,
                                  showNeutralFeedback = false) {
  const leftIsHigher = tp.left === tp.queryHigher;
  return {
    type: jsPsychLinkedListDisplay,
    query_left: tp.left,
    query_right: tp.right,
    query_left_rank: leftIsHigher ? tp.queryHigherRank : tp.queryLowerRank,
    query_right_rank: leftIsHigher ? tp.queryLowerRank : tp.queryHigherRank,
    correct_side: tp.correctSide,
    slots: tp.slots,
    response_deadline: responseDeadline,
    show_feedback: showFeedback,
    show_neutral_feedback: showNeutralFeedback,
    ordinal_distance: tp.ordinalDistance,
    context_hops: tp.contextHops,
    num_context_pairs: tp.numContextPairs,
    icl_consistent_side: tp.iclConsistentSide ?? null,
    phase: tp.phase,
    icl_ordering: tp.iclOrderingId ?? null,
    context_display: tp.contextDisplay,
    chain_order_json: JSON.stringify(tp.chain),
    inserted_distractor_positions_json: JSON.stringify(tp.distractorPositions),
    inserted_distractor_ids_json: JSON.stringify(tp.distractorIds || []),
    inserted_distractor_rank_buckets_json: JSON.stringify(tp.distractorRankBuckets || []),
    swap_distractor_id: tp.swapDistractorId ?? null,
    swap_distractor_rank_bucket: tp.swapDistractorRankBucket ?? null,
    swapped_item_id: tp.swappedItemId ?? null,
  };
}

// --- Practice ---

// The practice orderings, drawn once: the query-only block has its own three items; the
// single-step and multistep blocks share the seven practice items.
let practiceOrdering = null;
let queryOnlyPracticeOrdering = null;

function ensurePracticeOrdering() {
  if (!practiceOrdering) {
    practiceOrdering = shuffledCopy(stimuliState.practiceItems.map(i => i.id));
  }
  return practiceOrdering;
}

function ensureQueryOnlyPracticeOrdering() {
  if (!queryOnlyPracticeOrdering) {
    queryOnlyPracticeOrdering = shuffledCopy(stimuliState.queryOnlyPracticeItems.map(i => i.id));
  }
  return queryOnlyPracticeOrdering;
}

/**
 * The query-only practice block (block 1): adjacent pairs of three items, no pair row; the
 * preferences can be learned from the feedback alone.
 *
 * @param {object} jsPsych
 * @returns {object[]} Timeline nodes.
 */
export function buildQueryOnlyPracticeTrials(jsPsych) {
  const ordering = ensureQueryOnlyPracticeOrdering();
  const blockSize = CONFIG.numQueryOnlyPracticeTrials;
  const retryBlockSize = CONFIG.numQueryOnlyPracticeRetryTrials;
  const phases = ['practice_query', 'practice_query_extra'];

  return buildPracticeBlock(jsPsych, ordering, blockSize, phases,
    (ord, phase) => generateOneQueryOnlyPracticeTrialParams(ord, phase),
    'query', retryBlockSize);
}

/**
 * The single-step practice block (block 2): adjacent pairs, full display.
 *
 * @param {object} jsPsych
 * @returns {object[]} Timeline nodes.
 */
export function buildSinglehopPracticeTrials(jsPsych) {
  const ordering = ensurePracticeOrdering();
  const blockSize = CONFIG.numSinglehopPracticeTrials;
  const phases = ['practice_singlehop', 'practice_singlehop_extra'];

  return buildPracticeBlock(jsPsych, ordering, blockSize, phases,
    (ord, phase) => generateOneAdjacentPracticeTrialParams(ord, phase),
    'singlehop');
}

/**
 * The multistep practice block (block 3): pairs at symbolic distance 2 or 3.
 *
 * @param {object} jsPsych
 * @returns {object[]} Timeline nodes.
 */
export function buildMultiHopPracticeTrials(jsPsych) {
  const ordering = ensurePracticeOrdering();
  const blockSize = CONFIG.numMultiHopPracticeTrials;
  const phases = ['practice_multihop', 'practice_multihop_extra'];

  return buildPracticeBlock(jsPsych, ordering, blockSize, phases,
    (ord, phase) => generateOneMultiHopPracticeTrialParams(ord, phase),
    'multihop');
}

/**
 * A practice block and its retry block. The retry block's trials are built once and shown
 * again on every retry.
 *
 * @param {object} jsPsych
 * @param {string[]} ordering - The practice ordering.
 * @param {number} blockSize - Trials in the first block.
 * @param {string[]} phases - [phase of the first block, phase of the retry block].
 * @param {Function} generator - (ordering, phase) => TrialParams.
 * @param {string} blockId - 'query', 'singlehop' or 'multihop'.
 * @param {?number} [retryBlockSize=null] - Trials per retry block (default
 *   CONFIG.numExtraPracticeTrials).
 * @returns {object[]} Timeline nodes.
 */
function buildPracticeBlock(jsPsych, ordering, blockSize, phases, generator, blockId,
                            retryBlockSize = null) {
  const [initialPhase, extraPhase] = phases;
  const retrySize = retryBlockSize ?? CONFIG.numExtraPracticeTrials;

  function makePracticeNodes(n, phase) {
    const nodes = [];
    for (let t = 0; t < n; t++) {
      const tp = generator(ordering, phase);
      nodes.push(trialParamsToJsPsychNode(tp, CONFIG.responseDeadlineMs, true));
    }
    return nodes;
  }

  practiceState.attempts[blockId] = 1;
  const nodes = makePracticeNodes(blockSize, initialPhase);

  // A retry block runs, without notice, while accuracy on the block just completed is below
  // the threshold, at most practiceMaxRetries times; the session then moves on either way.
  let retries = 0;
  const decideRetry = () => {
    const compareSize = retries === 0 ? blockSize : retrySize;
    const recent = jsPsych.data.get().filter(
      t => t.phase === initialPhase || t.phase === extraPhase
    ).last(compareSize).values();
    if (recent.length < compareSize) return false;
    const acc = recent.filter(t => t.is_correct).length / recent.length;
    if (acc < CONFIG.practiceAccuracyThreshold && retries < CONFIG.practiceMaxRetries) {
      retries++;
      practiceState.attempts[blockId]++;
      return true;
    }
    return false;
  };

  nodes.push({
    timeline: makePracticeNodes(retrySize, extraPhase),
    conditional_function: decideRetry,
    loop_function: decideRetry,
  });

  return nodes;
}

// --- Learning phase ---

/**
 * The learning phase: CONFIG.numTrainingTrials trials with feedback and a break after every
 * CONFIG.trainingBreakFrequency trials. A random CONFIG.iwlDisplayProportionTraining of them
 * (10 of 100) show the context masked.
 *
 * @param {object} jsPsych
 * @returns {object[]} Timeline nodes.
 */
export function buildTrainingBlock(jsPsych) {
  const total = CONFIG.numTrainingTrials;
  const nodes = [];

  const numMasked = Math.round(total * CONFIG.iwlDisplayProportionTraining);
  const maskedIndices = new Set(
    shuffledIndices(total).slice(0, numMasked)
  );

  nodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: '',
    choices: 'NO_KEYS',
    trial_duration: 0,
    on_load: () => {
      showPhaseProgress('Learning phase');
      showPerformanceTracker();
    },
    data: { phase: 'progress_setup' },
  });

  let trainingCount = 0;

  for (let t = 0; t < total; t++) {
    const tp = maskedIndices.has(t)
      ? generateOneMaskedTrainingTrialParams()
      : generateOneTrainingTrialParams();
    const trialNode = trialParamsToJsPsychNode(tp, CONFIG.responseDeadlineMs, true);

    // The points counter changes when the feedback appears.
    trialNode.on_feedback = (data) => updatePerformanceTracker(data.is_correct);

    const origOnFinish = trialNode.on_finish;
    trialNode.on_finish = (data) => {
      if (origOnFinish) origOnFinish(data);
      trainingCount++;
      updatePhaseProgress(trainingCount, total);
    };

    nodes.push(trialNode);

    if ((t + 1) % CONFIG.trainingBreakFrequency === 0 && t + 1 < total) {
      const breakAt = t + 1;
      nodes.push(buildBreakNode(breakAt, total, 'the learning phase', true, 'training'));
    }
  }

  nodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: '',
    choices: 'NO_KEYS',
    trial_duration: 0,
    on_load: () => {
      removePerformanceTracker();
      removePhaseProgress();
    },
    data: { phase: 'progress_teardown' },
  });

  return nodes;
}

// --- Tests ---
// No correct/incorrect feedback: the chosen image is outlined and the next trial waits for
// Space (neutral feedback).

/** @param {Array<object>} rankPairs - From generateTestPairHistogram(). */
export function buildICLTestBlock(rankPairs) {
  const trials = generateICLTestTrials(rankPairs);
  return trials.map(tp => trialParamsToJsPsychNode(
    tp, CONFIG.testResponseDeadlineMs, false, true));
}

/** @param {Array<object>} rankPairs - From generateTestPairHistogram(). */
export function buildIWLTestBlock(rankPairs) {
  const trials = generateIWLTestTrials(rankPairs);
  return trials.map(tp => trialParamsToJsPsychNode(
    tp, CONFIG.testResponseDeadlineMs, false, true));
}

/** @param {Array<object>} rankPairs - From generateTestPairHistogram(). */
export function buildArbitrageTestBlock(rankPairs) {
  const trials = generateArbitrageTestTrials(rankPairs);
  return trials.map(tp => trialParamsToJsPsychNode(
    tp, CONFIG.testResponseDeadlineMs, false, true));
}

// --- Comprehension checks ---
//
// An attempt is one screen per question (rows with phase comprehension_<blockId>_q), then a
// result screen (phase comprehension_<blockId>). Every answer must be correct. After a failed
// attempt the participant goes back to the first page of the block's instructions and tries
// again; after CONFIG.comprehensionMaxRetries + 1 failed attempts the session ends. Each check
// has its own count of attempts.

/**
 * Shuffle the answer options of each question, at the start of each attempt. The shuffled
 * questions are kept in window.__compQuestions, where each question screen reads its own.
 *
 * @param {string} blockId
 * @returns {Array} The shuffled questions.
 */
function _shuffleQuestionsForBlock(blockId) {
  const questions = resolveBlockQuestions(blockId);
  const shuffledQs = questions.map(q => {
    const correctText = q.options[q.correct];
    const shuffledOptions = shuffledCopy(q.options);
    const newCorrectIdx = shuffledOptions.indexOf(correctText);
    return { ...q, options: shuffledOptions, correct: newCorrectIdx };
  });
  window.__compQuestions = shuffledQs;
  return shuffledQs;
}

/** One question screen (questions are numbered from 1). */
function _buildSingleQuestionHTML(q, qi, totalQ) {
  let html = '<div class="comprehension-check">';
  html += `<p class="comprehension-progress">Question ${qi + 1} of ${totalQ}</p>`;
  html += `<div class="comprehension-question" id="wrap-${q.id}"><p><strong>${q.text}</strong></p>`;
  for (let i = 0; i < q.options.length; i++) {
    html += `<label><input type="radio" name="${q.id}" value="${i}"> ${q.options[i]}</label>`;
  }
  html += '</div>';
  html += '<p id="comprehension-error" class="comprehension-error" style="display:none;"></p>';
  html += '<button id="comprehension-submit" class="jspsych-btn" style="margin-top:1rem;">Next</button>';
  html += '</div>';
  return html;
}

/** A question screen. The first question of an attempt also starts the attempt. */
function _buildPerQuestionTrial(jsPsych, blockId) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: () => {
      const qi = jsPsych.evaluateTimelineVariable('qi');
      const totalQ = jsPsych.evaluateTimelineVariable('totalQ');
      if (qi === 0) {
        comprehensionState.attempts[blockId]++;
        _shuffleQuestionsForBlock(blockId);
      }
      const q = window.__compQuestions[qi];
      return _buildSingleQuestionHTML(q, qi, totalQ);
    },
    choices: 'NO_KEYS',
    data: {
      phase: `comprehension_${blockId}_q`,
      comprehension_block_id: blockId,
    },
    on_load: () => {
      const qi = jsPsych.evaluateTimelineVariable('qi');
      const q = window.__compQuestions[qi];
      const attempt = comprehensionState.attempts[blockId];
      const t0 = performance.now();

      const submitBtn = document.getElementById('comprehension-submit');
      const errorEl = document.getElementById('comprehension-error');

      submitBtn.addEventListener('click', () => {
        const sel = document.querySelector(`input[name="${q.id}"]:checked`);
        if (!sel) {
          errorEl.textContent = 'Please choose an answer.';
          errorEl.style.display = 'block';
          return;
        }
        errorEl.style.display = 'none';
        const chosen = parseInt(sel.value, 10);
        const isCorrect = chosen === q.correct;
        // The response is the position of the option as shown (after the shuffle).
        jsPsych.finishTrial({
          comprehension_question_id: q.id,
          comprehension_question_index: qi,
          comprehension_response: chosen,
          comprehension_response_text: q.options[chosen],
          comprehension_question_rt_ms: Math.round(performance.now() - t0),
          is_question_correct: isCorrect,
          comprehension_attempt_number: attempt,
        });
      });
    },
  };
}

/**
 * The result screen of an attempt, from the attempt's question rows. A passed attempt, and a
 * failed last attempt, finish at once without showing anything; a failed attempt with attempts
 * left says so and offers to try again.
 */
function _buildAggregatorTrial(jsPsych, blockId, totalQ) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: () => {
      const qRows = jsPsych.data.get()
        .filter({ phase: `comprehension_${blockId}_q`, comprehension_block_id: blockId })
        .last(totalQ)
        .values();

      const responses = {};
      const correctness = {};
      let allCorrect = qRows.length === totalQ;
      for (const row of qRows) {
        const id = row.comprehension_question_id;
        responses[id] = row.comprehension_response;
        correctness[id] = !!row.is_question_correct;
        if (!row.is_question_correct) allCorrect = false;
      }

      const attempt = comprehensionState.attempts[blockId];
      const maxAttempts = CONFIG.comprehensionMaxRetries + 1;
      const isExhausted = !allCorrect && attempt >= maxAttempts;

      // Handed to on_load, which shows the result.
      window.__compAggregate = { responses, correctness, allCorrect, attempt, maxAttempts, isExhausted };

      if (allCorrect || isExhausted) return '';

      let html = '<div class="comprehension-check">';
      html += '<h2>Quick Check — Results</h2>';
      html += '<div id="comprehension-result" class="comprehension-result"></div>';
      html += '<button id="comprehension-continue" class="jspsych-btn" style="margin-top:1rem;">Continue</button>';
      html += '</div>';
      return html;
    },
    choices: 'NO_KEYS',
    data: {
      phase: `comprehension_${blockId}`,
      comprehension_block_id: blockId,
    },
    on_load: () => {
      const { responses, correctness, allCorrect, attempt, maxAttempts, isExhausted } = window.__compAggregate || {};

      if (allCorrect || isExhausted) {
        if (isExhausted) {
          failureState.failed = true;
          failureState.check = `comprehension_${blockId}_exhausted`;
        }
        // Finish on the next turn, after the plugin has set up the screen.
        setTimeout(() => {
          jsPsych.finishTrial({
            is_comprehension_passed: !!allCorrect,
            is_comprehension_exhausted: !!isExhausted,
            comprehension_block_id: blockId,
            comprehension_attempt_number: attempt,
            comprehension_responses_json: JSON.stringify(responses),
            comprehension_correct_json: JSON.stringify(correctness),
          });
        }, 0);
        return;
      }

      const resultEl = document.getElementById('comprehension-result');
      const continueBtn = document.getElementById('comprehension-continue');

      const remaining = maxAttempts - attempt;
      const tryWord = remaining === 1 ? 'try' : 'tries';
      resultEl.innerHTML = `
        <p class="comprehension-failed"><strong>You did not pass.</strong></p>
        <p>You'll go back through the instructions and try again.</p>
        <p class="comprehension-attempts-remaining">You have ${remaining} ${tryWord} remaining.</p>`;
      continueBtn.textContent = 'Try again';

      continueBtn.addEventListener('click', () => {
        comprehensionState.needsReset[blockId] = true;
        jsPsych.finishTrial({
          is_comprehension_passed: false,
          is_comprehension_exhausted: false,
          comprehension_block_id: blockId,
          comprehension_attempt_number: attempt,
          comprehension_responses_json: JSON.stringify(responses),
          comprehension_correct_json: JSON.stringify(correctness),
        });
      });
    },
  };
}

/**
 * One attempt of a comprehension check: the question screens, then the result screen.
 *
 * @param {object} jsPsych
 * @param {string} blockId - 'query', 'singlehop', 'multihop' or 'final'.
 * @returns {object} jsPsych timeline node.
 */
export function buildComprehensionCheck(jsPsych, blockId) {
  const totalQ = resolveBlockQuestions(blockId).length;
  return {
    timeline: [
      {
        timeline: [_buildPerQuestionTrial(jsPsych, blockId)],
        timeline_variables: Array.from({ length: totalQ }, (_, i) => ({
          qi: i, totalQ,
        })),
      },
      _buildAggregatorTrial(jsPsych, blockId, totalQ),
    ],
  };
}

/**
 * A block's instructions followed by its comprehension check, repeated after a failed attempt
 * while attempts are left.
 *
 * @param {object} jsPsych
 * @param {string} blockId - 'query', 'singlehop', 'multihop' or 'final'.
 * @param {Function} buildInstructionsNode - Returns the block's instructions node.
 * @returns {object} jsPsych timeline node.
 */
export function buildComprehensionBlock(jsPsych, blockId, buildInstructionsNode) {
  return {
    timeline: [
      buildInstructionsNode(),
      buildComprehensionCheck(jsPsych, blockId),
    ],
    loop_function: (data) => {
      const lastCC = data.filter({ phase: `comprehension_${blockId}` }).last(1).values()[0];
      if (!lastCC) return false;
      if (lastCC.is_comprehension_passed) return false;
      if (lastCC.is_comprehension_exhausted) return false;
      return true;
    },
  };
}

/**
 * The last screen of a session that failed a comprehension check: it saves the session record
 * and stays on screen; nothing follows.
 *
 * @param {object} options
 * @param {Function} options.silenceBeforeUnload - Stop asking before the page is left.
 * @param {Function} options.finalizeAndSave - Save the session record.
 * @returns {object} jsPsych timeline node.
 */
export function buildFailedScreenTrial({ silenceBeforeUnload, finalizeAndSave }) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: COMPREHENSION_FAILED_HTML,
    choices: 'NO_KEYS',
    trial_duration: null,
    data: {
      phase: 'comprehension_failed',
    },
    on_load: () => {
      try {
        silenceBeforeUnload();
      } catch (e) { console.error('[Experiment] silenceBeforeUnload threw:', e); }
      try {
        finalizeAndSave();
      } catch (e) {
        console.error('[Experiment] save failed:', e);
      }
    },
  };
}

// --- Practice preamble and closing screen ---

/** The reminders shown before a practice block; each block adds to the previous one's. */
function summaryBulletsFor(blockId) {
  const baseQuery = [
    '<li>Choose the object the aliens prefer <strong>more</strong></li>',
    '<li><kbd>F</kbd> = left, <kbd>J</kbd> = right</li>',
    '<li>Use the feedback after each trial to <strong>learn</strong></li>',
  ];

  const clueBullets = [
    '<li>The pair list below the question shows <strong>clues</strong> about the aliens\' preferences</li>',
    '<li>The <strong>arrow</strong> in each clue points to the object the aliens prefer <strong>more</strong></li>',
    '<li>In each clue, the preferred object is always shown on <strong>top</strong></li>',
  ];
  const multiHop = [
    '<li>Sometimes <strong>multiple clues</strong> are needed to answer a question</li>',
  ];

  switch (blockId) {
    case 'query':     return baseQuery;
    case 'singlehop': return [...baseQuery, ...clueBullets];
    case 'multihop':  return [...baseQuery, ...clueBullets, ...multiHop];
    default:          return baseQuery;
  }
}

/**
 * The screen after a practice block; the next instructions are checked too.
 *
 * @param {string} blockId
 * @returns {object} jsPsych timeline node.
 */
export function buildPostPracticeScreen(blockId) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="break-screen">
        <h2>Great work!</h2>
        <p>You've completed the practice.</p>
        <p>There are still more instructions to read.</p>
        <p>You'll also be <strong>tested</strong> on the next set of instructions.</p>
        <p>Press <kbd>Space</kbd> to continue.</p>
      </div>
    `,
    choices: [' '],
    data: { phase: `post_practice_${blockId}` },
  };
}

/**
 * The screen between a passed comprehension check and its practice block, with reminders.
 *
 * @param {string} blockId
 * @returns {object} jsPsych timeline node.
 */
export function buildPracticePreamble(blockId) {
  const bullets = summaryBulletsFor(blockId).join('\n          ');
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="break-screen">
        <h2>You passed!</h2>
        <p>Quick reminder before practice begins:</p>
        <div class="summary-box">
          <ul>
            ${bullets}
          </ul>
        </div>
        ${helpReminderHTML()}
        <p>Press <kbd>Space</kbd> to begin practice.</p>
      </div>
    `,
    choices: [' '],
    data: { phase: `practice_preamble_${blockId}` },
  };
}
