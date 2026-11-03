/**
 * The questions of the four comprehension checks, as participants saw them.
 *
 * Each check (blocks `query`, `singlehop`, `multihop`, and `final` after the experiment
 * overview) asks four multiple-choice questions; all four must be answered correctly. Some
 * questions recur in later checks.
 *
 * A question is {id, text, options, correct}, where `correct` is the index of the correct
 * option before the options are shuffled. A question about the session's own items gives
 * `textFn` and `optionsFn` instead, resolved when it is shown (resolveQuestion).
 *
 * @module comprehension-questions
 */

import { stimuliState } from './stimuli.js';
import { formatLabel } from './utils.js';

// --- Block 1: query basics ---

const Q_GOAL = {
  id: 'q_goal',
  text: 'What is your job in this experiment?',
  options: [
    'Choose the object the aliens prefer more',
    'Choose the object the aliens prefer less',
    'Choose the object the aliens have seen before',
    'Choose the object the aliens have not seen before',
  ],
  correct: 0,
};

const Q_KEYS = {
  id: 'q_keys',
  text: 'Which keys do you press to respond?',
  options: [
    'F for the left object, J for the right object',
    'Left arrow for the left object, Right arrow for the right object',
    'D for the left object, K for the right object',
    'G for the left object, H for the right object',
  ],
  correct: 0,
};

const Q_INCORRECT_CONSEQUENCE = {
  id: 'q_incorrect_consequence',
  text: 'What happens after you answer incorrectly?',
  options: [
    'Your choice is highlighted in red, and you move on immediately to the next trial',
    'Your choice is highlighted in red, and there is a brief delay before you can continue',
    'The experiment ends',
    'You go back to the previous trial',
  ],
  correct: 1,
};

const Q_STRATEGY = {
  id: 'q_strategy',
  text: 'How can you figure out which objects to choose?',
  options: [
    'Guess randomly — there is no way to know',
    'Use the feedback after each trial to learn the aliens’ preferences',
    'Pick the most valuable object',
    'Pick the object that hasn’t appeared previously',
  ],
  correct: 1,
};

// --- Block 2: the full display, one step ---
const Q_ARROW_MEANING = {
  id: 'q_arrow_meaning',
  text: 'What does an arrow pointing from one object to another mean?',
  options: [
    'The arrow points to the object the aliens prefer more',
    'The arrow points to the object the aliens prefer less',
    "The object at the arrow's tail is more important to remember",
    'The arrow shows which object will appear in the next question',
  ],
  correct: 0,
};

const Q_TOP_POSITION = {
  id: 'q_top_position',
  text: 'How do the aliens arrange the two objects in each clue?',
  options: [
    'The preferred object is always shown on top',
    'The preferred object is always shown on bottom',
    'It changes from clue to clue',
    'They are arranged left-to-right by preference',
  ],
  correct: 0,
};

const Q_CLUES_PURPOSE = {
  id: 'q_clues_purpose',
  text: 'What is the row of paired objects below the question for?',
  options: [
    'They are clues about which objects the aliens prefer',
    'They are decorative — ignore them',
    'They show which objects the aliens have seen before',
    'They show which objects the aliens haven’t seen before',
  ],
  correct: 0,
};

const Q_CLUES_OPTIONAL = {
  id: 'q_clues_optional',
  text: 'When should you answer a question without using the clues?',
  options: [
    'Never — the clues are required on every trial',
    'When you already know the aliens’ preferences for the objects',
    'When the response keys are unavailable',
    'Whenever you don’t know the aliens’ preferences for the objects',
  ],
  correct: 1,
};

// --- Block 3: several steps ---

// The transitive question uses practice items 0, 1 and 2; the worked example in the
// instructions uses items 2, 3 and 4.
const Q_TRANSITIVE = {
  id: 'q_transitive',
  textFn: () => {
    const items = stimuliState.practiceItems;
    const X = formatLabel(items[0].label);
    const Y = formatLabel(items[1].label);
    const Z = formatLabel(items[2].label);
    return `If the aliens prefer ${X} over ${Y}, and prefer ${Y} over ${Z}, which do they prefer more between ${X} and ${Z}?`;
  },
  optionsFn: () => {
    const items = stimuliState.practiceItems;
    const X = formatLabel(items[0].label);
    const Z = formatLabel(items[2].label);
    return [
      X,
      Z,
      `The aliens prefer ${X} and ${Z} equally`,
      `You can’t tell unless there is a direct clue comparing ${X} and ${Z}`,
    ];
  },
  correct: 0, // X always correct (X > Y > Z by construction)
};

const Q_NUM_CLUES = {
  id: 'q_num_clues',
  text: 'How many clues might be relevant to a single question?',
  options: [
    'Always exactly one clue is relevant',
    'Always exactly two clues are relevant',
    'Sometimes one clue, sometimes more — you may need to combine multiple clues',
    'The clues are never relevant — you should ignore them',
  ],
  correct: 2,
};

const Q_MULTI_HOP_STRATEGY = {
  id: 'q_multi_hop_strategy',
  text: 'If no single clue directly compares the two objects in the question, what should you do?',
  options: [
    'Guess randomly',
    'Look for ways of connecting them with multiple clues',
    'Skip the question',
    'Always pick the left object',
  ],
  correct: 1,
};

// --- The final check, after the experiment overview ---
const Q_IWL_DISPLAY = {
  id: 'q_iwl_display',
  text: 'When you see gray boxes instead of the alien objects, what should you do?',
  options: [
    'Guess randomly',
    'Pick the more valuable object',
    'Rely on what you’ve learned previously',
    'Pick the object you’ve seen before',
  ],
  correct: 2,
};

const Q_FEEDBACK_PHASE = {
  id: 'q_feedback_phase',
  text: 'During which part of the experiment will you receive feedback after each trial?',
  options: [
    'During the learning phase only',
    'During the test phase only',
    'During both the learning and test phases',
    'Never — you don’t receive feedback at any point',
  ],
  correct: 0,
};

// --- The questions of each check ---

function getBlockPool(blockId) {
  switch (blockId) {
    case 'query':
      return [Q_GOAL, Q_KEYS, Q_INCORRECT_CONSEQUENCE, Q_STRATEGY];
    case 'singlehop':
      return [Q_CLUES_PURPOSE, Q_ARROW_MEANING, Q_TOP_POSITION, Q_CLUES_OPTIONAL];
    case 'multihop':
      return [Q_TRANSITIVE, Q_NUM_CLUES, Q_MULTI_HOP_STRATEGY, Q_ARROW_MEANING];
    case 'final':
      return [Q_IWL_DISPLAY, Q_FEEDBACK_PHASE, Q_CLUES_OPTIONAL, Q_NUM_CLUES];
    default:
      throw new Error(`getBlockPool: unknown blockId "${blockId}"`);
  }
}

const VALID_BLOCK_IDS = ['query', 'singlehop', 'multihop', 'final'];

/**
 * A question as shown: {id, text, options, correct}, with any session items filled in.
 *
 * @param {object} q - A question definition.
 * @returns {{id: string, text: string, options: string[], correct: number}}
 */
export function resolveQuestion(q) {
  const text = typeof q.text === 'string' ? q.text : q.textFn();
  const options = Array.isArray(q.options) ? q.options : q.optionsFn();
  const correct = q.correct;
  if (correct < 0 || correct >= options.length) {
    throw new Error(`resolveQuestion(${q.id}): correct index ${correct} out of range for ${options.length} options`);
  }
  return { id: q.id, text, options, correct };
}

/**
 * The questions of one check, as shown.
 * @param {string} blockId
 * @returns {Array<{id, text, options, correct}>}
 */
export function resolveBlockQuestions(blockId) {
  if (!VALID_BLOCK_IDS.includes(blockId)) {
    throw new Error(`resolveBlockQuestions: unknown blockId "${blockId}". Valid: ${VALID_BLOCK_IDS.join(', ')}.`);
  }
  return getBlockPool(blockId).map(resolveQuestion);
}
