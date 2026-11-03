/**
 * The instruction pages, as participants saw them.
 *
 * A page with a display is prose in a zone of fixed height above a static display (display.js
 * buildInstructionDisplay), whose pair row keeps its place even when empty, so nothing moves
 * from page to page. A page without a display lets the prose take the space it needs.
 *
 * The sequence: the warning page; block 1 (the query); block 2 (the full display, one step);
 * block 3 (several steps); the experiment overview; the summary before the learning phase; the
 * pages before the tests. Blocks 1-3 end with a page announcing their comprehension check.
 *
 * The examples use the practice items, never the items of the learning phase. They state
 * preferences among the practice items in the items' stored order; the practice blocks draw
 * their own ordering of the same items (js/trials.js), so a practice block can show a
 * preference opposite to an example's.
 *
 * @module instructions
 */

import { CONFIG, framesToMs } from './config.js';
import { stimuliState } from './stimuli.js';
import { buildInstructionDisplay } from './display.js';
import { formatLabel, buildFixedEndChain, assignSlotsToLinks } from './utils.js';

/**
 * The reminder of the help button on summary, preamble, break and transition screens. A <div>,
 * not a <p>, so that it stays centered inside .instruction-text-flow.
 * @returns {string}
 */
export function helpReminderHTML() {
  return '<div class="help-reminder">If you\'re ever confused or get stuck, use the help button (?) in the bottom-left corner.</div>';
}

// --- Helpers ---

/**
 * One instruction page: prose, and below it an optional display. With a display the prose sits
 * in a zone of fixed height (.instruction-text-top), so the display is in the same place on
 * every page of a block; without one it flows (.instruction-text-flow).
 *
 * @param {string} proseHTML - The prose (<h2>, <p>, <ul>).
 * @param {string} displayHTML - A buildInstructionDisplay() display, or ''.
 * @returns {string}
 */
function instructionPage(proseHTML, displayHTML = '') {
  const hasDisplay = !!displayHTML && displayHTML.trim() !== '';
  const proseClass = hasDisplay ? 'instruction-text-top' : 'instruction-text-flow';
  return `
    <div class="instruction-page">
      <div class="${proseClass}">${proseHTML}</div>
      ${displayHTML}
    </div>`;
}

/**
 * The pair row of the practice items (in their stored order) with their end distractors, its
 * pairs in random positions as on a trial.
 *
 * @returns {Array<object>} Slots of utils.assignSlotsToLinks.
 */
function makeShuffledPracticeSlots() {
  const items = stimuliState.practiceItems.map(i => i.id);
  const endHigh = stimuliState.practiceEndDistractors[0].id;
  const endLow = stimuliState.practiceEndDistractors[1].id;
  const { links } = buildFixedEndChain(items, endHigh, endLow);
  return assignSlotsToLinks(links);
}

// One arrangement per block, so a highlighted pair stays in its place from page to page.
const blockSlotCache = {
  singlehop: null,
  multihop: null,
};

function getBlockSlots(blockId) {
  if (!blockSlotCache[blockId]) {
    blockSlotCache[blockId] = makeShuffledPracticeSlots();
  }
  return blockSlotCache[blockId];
}

/** The position in the row of the pair higher-lower, or -1. */
function findSlotIndexByLink(slots, higher, lower) {
  for (const s of slots) {
    if (s.higher === higher && s.lower === lower) return s.pairIndex;
  }
  return -1;
}

const goalText = 'Select the objects the aliens prefer to earn points.';

// --- The warning page ---

/**
 * The first instruction page: the instructions will be checked, and failing the checks ends
 * the experiment. It opens block 1, so a failed check of block 1 returns to it.
 *
 * @returns {string[]}
 */
export function buildWarningPages() {
  return [
    instructionPage(`
      <h2>Please read carefully</h2>
      <p>The instructions you're about to read explain how this experiment works.
      <strong>You will be tested</strong> on your understanding of the instructions.</p>
      <p>If you fail the understanding checks too many times, the experiment will
      end and <strong>you will not receive a completion code</strong>.</p>
      <p>Take your time. Read every page carefully.</p>
    `),
  ];
}


// --- Block 1: the query ---

/**
 * Block 1: the cover story, the query, the keys, the feedback (correct, incorrect, too slow),
 * learning from feedback, the help button, and the comprehension check announcement. The
 * displays show the query alone, with two of the query-only practice items.
 *
 * @returns {string[]}
 */
export function buildQueryInstructionPages() {
  const items = stimuliState.queryOnlyPracticeItems;
  const qLeft = items[0].id;
  const qRight = items[1].id;
  const labelHigh = formatLabel(items[0].label);
  const labelLow  = formatLabel(items[1].label);

  const queryDisplay = (overrides = {}) => buildInstructionDisplay({
    queryLeft: qLeft, queryRight: qRight,
    showPairRow: false,
    showKeyHints: true,
    ...overrides,
  });

  return [
    // Page 1: the cover story.
    instructionPage(
      `<h2>Your task</h2>
       <p>An alien civilization has visited Earth and encountered everyday
       objects for the first time. The aliens have their own strange
       preferences for which objects they like more than others.</p>
       <p>Your job is to select the objects the aliens prefer. They’ll give you <strong>points</strong> for choosing the object they prefer more.</p>`
    ),

    // Page 2: the query.
    instructionPage(
      `<p>On each trial, you'll see <strong>two objects</strong> in the middle of the screen.
       Your job is to choose which one the aliens prefer more.</p>`,
      queryDisplay({ keyHintsOpacity: 0 })
    ),

    // Page 3: the keys.
    instructionPage(
      `<p>Press <kbd>F</kbd> to choose the <strong>left</strong> object.
       Press <kbd>J</kbd> to choose the <strong>right</strong> object.</p>`,
      queryDisplay({ keyHintsOpacity: 1 })
    ),

    // Page 4: feedback after a correct answer.
    instructionPage(
      `<p>After each answer, you'll see whether you were correct.
       If correct, your chosen object is highlighted in <strong style="color:#3a8a3a">green</strong>.</p>`,
      queryDisplay({
        selectedSide: 'left', selectedCorrect: true,
        feedbackBorderColor: '#3a8a3a',
        feedbackHTML: `
          <div class="feedback-text feedback-correct">Correct!</div>
          <div class="feedback-relation">
            The aliens prefer <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.
          </div>
          <div class="feedback-continue">Press <kbd>Space</kbd> to continue.</div>`,
      })
    ),

    // Page 5: feedback after an error.
    instructionPage(
      `<p>If incorrect, your choice is highlighted in
       <strong style="color:#c44a3a">red</strong>, and there will be a brief
       <strong>delay</strong> before you can continue.</p>`,
      queryDisplay({
        selectedSide: 'right', selectedCorrect: false,
        feedbackBorderColor: '#c44a3a',
        feedbackHTML: `
          <div class="feedback-text feedback-incorrect">Incorrect.</div>
          <div class="feedback-relation">
            The aliens prefer <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.
          </div>
          <div class="feedback-continue">Press <kbd>Space</kbd> to continue.</div>`,
      })
    ),

    // Page 6: feedback after a timeout.
    instructionPage(
      `<p>If you take too long to respond, the trial will end on its own.
       The correct answer is shown in green, and the incorrect one in red,
       so you can still learn from it.</p>`,
      queryDisplay({
        leftHighlight: 'correct', rightHighlight: 'incorrect',
        feedbackBorderColor: '#c44a3a',
        feedbackHTML: `
          <div class="feedback-text feedback-incorrect">Too slow!</div>
          <div class="feedback-relation">
            The aliens prefer <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.
          </div>
          <div class="feedback-continue">Press <kbd>Space</kbd> to continue.</div>`,
      })
    ),

    // Page 7: learning from the feedback.
    instructionPage(
      `<p>You can use the feedback after each trial to <strong>learn</strong>
       which objects the aliens prefer.</p>`,
      queryDisplay({
        selectedSide: 'right', selectedCorrect: false,
        feedbackBorderColor: '#c44a3a',
        feedbackHTML: `
          <div class="feedback-text feedback-incorrect">Incorrect.</div>
          <div class="feedback-relation">
            The aliens prefer <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.
          </div>
          <div class="feedback-continue">Press <kbd>Space</kbd> to continue.</div>`,
      })
    ),

    // Page 8: the help button, shown on this page (queryHelpIntroPageIndex()).
    instructionPage(
      `<h2>A help button is available</h2>
       <p>A small <strong>?</strong> button is in the bottom-left corner
       of the screen — you can see it now.</p>
       <p>It shows a short summary of the rules for whatever you're
       currently doing. The content updates as you progress.</p>
       <p>Using it is optional and won't pause anything.</p>
       <p>Try clicking it now to see how it looks.
       <strong>Next</strong> will become available once you do.</p>`
    ),

    // Page 9: the comprehension check announcement.
    instructionPage(
      `<h2>Ready to be tested?</h2>
       <p>Next we'll ask you a few quick questions to make sure you understand.</p>
       <p>You can still go back to previous pages right now if you want to
       review them before the test. When you're ready, press <strong>Next</strong> to begin.</p>`
    ),
  ];
}

/**
 * The index of the help-button page in buildQueryInstructionPages() (the second to last).
 * @returns {number}
 */
export function queryHelpIntroPageIndex() {
  return buildQueryInstructionPages().length - 2;
}

// --- Block 2: the full display, one step ---

/**
 * Block 2: the pair row as clues, how to read a clue (arrow and position), a clue that answers
 * the query (the pair items[0]-items[1], highlighted), clues are optional, and the comprehension
 * check announcement.
 *
 * @returns {string[]}
 */
export function buildSinglehopInstructionPages() {
  const items = stimuliState.practiceItems;
  const qLeft = items[0].id;
  const qRight = items[1].id;
  const labelHigh = formatLabel(items[0].label);
  const labelLow  = formatLabel(items[1].label);

  const slots = getBlockSlots('singlehop');
  const highlightedSlotIdx = findSlotIndexByLink(slots, items[0].id, items[1].id);
  const highlightSlots = highlightedSlotIdx >= 0 ? [highlightedSlotIdx] : [];

  const fullDisplay = (overrides = {}) => buildInstructionDisplay({
    queryLeft: qLeft, queryRight: qRight,
    slots,
    showPairRow: true,
    showKeyHints: true,
    ...overrides,
  });

  return [
    // Page 1: the full display.
    instructionPage(
      `<p>Feedback can be used to learn the alien preferences.</p>
       <p>However, <strong>clues</strong> will also be included below the question.</p>
       <p>The full display looks like this:</p>`,
      fullDisplay({ keyHintsOpacity: 0 })
    ),

    // Page 2: the clues.
    instructionPage(
      `<p>Each <strong>pair</strong> of connected objects in the row below is a clue about the aliens' preferences.</p>`,
      fullDisplay({ keyHintsOpacity: 0 })
    ),

    // Page 3: reading a clue.
    instructionPage(
      `<p>In each clue, the <strong>preferred</strong> object is shown
            on <strong>top</strong>, and the <strong>arrow points to it</strong>.</p>`,
      fullDisplay({ keyHintsOpacity: 0 })
    ),

    // Page 4: the clue that answers the query.
    instructionPage(
      `<p>Here, the clue says the aliens prefer
       <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.</p>
       <p>So the answer is <strong>${labelHigh}</strong> (the left object).</p>`,
      fullDisplay({
        pairRowOpacity: 0.3, highlightSlots,
        keyHintsOpacity: 0,
      })
    ),

    // Page 5: clues are optional.
    instructionPage(
      `<p>Tip: the clues are there to help, but you don't always need to use them.</p>
       <p>If you already know the answer, you might not need to look at the clues.</p>`,
      fullDisplay({ keyHintsOpacity: 0 })
    ),

    // Page 6: the comprehension check announcement.
    instructionPage(
      `<h2>Ready to be tested?</h2>
       <p>Next we'll ask you a few quick questions about the clues.</p>
       <p>You can still go back to previous pages right now if you want to
       review them before the test. When you're ready, press <strong>Next</strong>.</p>`
    ),
  ];
}

// --- Block 3: several steps ---

/**
 * Block 3: several clues may be needed; a worked transitive example (X over Y and Y over Z, so
 * X over Z, with the practice items 2, 3 and 4); combining more than two clues (X to W, items 2
 * to 5); and the comprehension check announcement.
 *
 * @returns {string[]}
 */
export function buildMultihopInstructionPages() {
  const items = stimuliState.practiceItems;
  const X = items[2], Y = items[3], Z = items[4], W = items[5];
  const xLabel = formatLabel(X.label);
  const yLabel = formatLabel(Y.label);
  const zLabel = formatLabel(Z.label);
  const wLabel = formatLabel(W.label);

  // The positions in the row of the clues X-Y, Y-Z and Z-W.
  const slots = getBlockSlots('multihop');
  const xy = findSlotIndexByLink(slots, X.id, Y.id);
  const yz = findSlotIndexByLink(slots, Y.id, Z.id);
  const zw = findSlotIndexByLink(slots, Z.id, W.id);
  const twoHopHighlight = [xy, yz].filter(i => i >= 0);
  const xyOnlyHighlight = [xy].filter(i => i >= 0);
  const threeHopHighlight = [xy, yz, zw].filter(i => i >= 0);

  // The query X vs Z (two steps).
  const twoHopDisplay = (overrides = {}) => buildInstructionDisplay({
    queryLeft: X.id, queryRight: Z.id,
    slots,
    showPairRow: true,
    showKeyHints: true,
    ...overrides,
  });

  // The query X vs W (three steps).
  const threeHopDisplay = (overrides = {}) => buildInstructionDisplay({
    queryLeft: X.id, queryRight: W.id,
    slots,
    showPairRow: true,
    showKeyHints: true,
    ...overrides,
  });

  return [
    // Page 1: several clues.
    instructionPage(
      `<p>The clues can also be more complex. Sometimes <strong>multiple clues</strong>
       are relevant to a single question.</p>
       <p>Here's an example: the question asks about two objects, and the clues
       you need are highlighted below.</p>`,
      twoHopDisplay({
        pairRowOpacity: 0.3, highlightSlots: twoHopHighlight,
        keyHintsOpacity: 0,
      })
    ),

    // Pages 2a-2c: the worked example, one sentence at a time.
    instructionPage(
      `<p>One clue shows that the aliens prefer
       <strong>${xLabel}</strong> over <strong>${yLabel}</strong>.</p>`,
      twoHopDisplay({
        pairRowOpacity: 0.3, highlightSlots: xyOnlyHighlight,
        keyHintsOpacity: 0,
      })
    ),

    instructionPage(
      `<p>One clue shows that the aliens prefer
       <strong>${xLabel}</strong> over <strong>${yLabel}</strong>.</p>
       <p>Another shows that they prefer <strong>${yLabel}</strong> over
       <strong>${zLabel}</strong>.</p>`,
      twoHopDisplay({
        pairRowOpacity: 0.3, highlightSlots: twoHopHighlight,
        keyHintsOpacity: 0,
      })
    ),

    instructionPage(
      `<p>One clue shows that the aliens prefer
       <strong>${xLabel}</strong> over <strong>${yLabel}</strong>.</p>
       <p>Another shows that they prefer <strong>${yLabel}</strong> over
       <strong>${zLabel}</strong>.</p>
       <p>So the aliens prefer <strong>${xLabel}</strong> over
       <strong>${zLabel}</strong>.</p>`,
      twoHopDisplay({
        pairRowOpacity: 0.3, highlightSlots: twoHopHighlight,
        keyHintsOpacity: 0,
      })
    ),

    // Page 3: combining more than two clues.
    instructionPage(
      `<p>If no single clue <em>directly</em> compares the two objects in the question,
       look for ways of connecting them with multiple clues.</p>
       <p>You may need to combine <strong>more than two clues</strong>, depending on the
       question.</p>`,
      threeHopDisplay({
        pairRowOpacity: 0.3, highlightSlots: threeHopHighlight,
        keyHintsOpacity: 0,
      })
    ),

    // Page 4: the comprehension check announcement.
    instructionPage(
      `<h2>Ready to be tested?</h2>
       <p>Next we'll check that you understand how to combine clues.</p>
       <p>You can still go back to previous pages right now if you want to
       review them before the test. When you're ready, press <strong>Next</strong>.</p>`
    ),
  ];
}

// --- The experiment overview ---

/** The practice pair row with every image masked, for the pages that show the masked context. */
function makeTestContextSlots() {
  const items = stimuliState.practiceItems.map(i => i.id);
  const endHigh = stimuliState.practiceEndDistractors[0].id;
  const endLow = stimuliState.practiceEndDistractors[1].id;
  const { links } = buildFixedEndChain(items, endHigh, endLow);
  const slots = assignSlotsToLinks(links);
  for (const s of slots) {
    s.maskItem = true;
  }
  return slots;
}

/**
 * The two overview pages that show the masked context.
 * @returns {string[]}
 */
function buildTestContextOverviewPages() {
  const slots = makeTestContextSlots();
  const items = stimuliState.practiceItems;
  const qLeft = items[2].id;
  const qRight = items[4].id;

  const demoDisplay = (overrides = {}) => buildInstructionDisplay({
    queryLeft: qLeft, queryRight: qRight,
    slots,
    showPairRow: true,
    showKeyHints: true,
    keyHintsOpacity: 0,
    ...overrides,
  });

  return [
    instructionPage(
      `<p>Sometimes the objects in the clues will be replaced with
         <strong>gray boxes</strong>. Here is what that looks like:</p>`,
      demoDisplay()
    ),
    instructionPage(
      `<p>Gray boxes mean the clues <strong>cannot</strong> help —
         you'll need to rely on <strong>what you've learned</strong>.</p>`,
      demoDisplay()
    ),
  ];
}

/**
 * The experiment overview after the practice blocks: the two phases, the points and the
 * masked context. Its comprehension check follows.
 *
 * @returns {string[]}
 */
export function buildExperimentOverview() {
  const pages = [];

  pages.push(
    instructionPage(
      `<h2>How the experiment works</h2>
       <p>The experiment has two parts: a <strong>learning phase</strong> and a
       <strong>test phase</strong>, followed by a short questionnaire.</p>
       <p>During the learning phase, you'll receive feedback after every trial.
       During the test phase, you will <strong>not</strong> receive feedback.</p>
       <p>Your performance during both phases determines your <strong>bonus payment</strong>.</p>
       ${helpReminderHTML()}`
    )
  );

  pages.push(
    instructionPage(
      `<p>During learning, you'll see a point tracker in the
         <strong>top-right corner</strong> of the screen.
         It won't be visible during the test phase.</p>
         <div class="perf-tracker-demo">
           <span class="perf-tracker-icon">⭐</span> 10 pts
         </div>`
    )
  );

  pages.push(...buildTestContextOverviewPages());

  return pages;
}

/**
 * The summary before the learning phase.
 * @returns {string[]}
 */
export function buildPreTrainingSummary() {
  const extraBullets = [
    '<li><strong>Points:</strong> You\'ll see your points during learning, but not during the test phase.</li>',
    '<li><strong>Bonus:</strong> Your performance determines your <strong>bonus payment</strong>.</li>',
  ];

  return [
    instructionPage(
      `<h2>Summary</h2>
       <div class="summary-box">
         <ul>
           <li><strong>Goal:</strong> ${goalText}</li>
           <li><strong>Controls:</strong> <kbd>F</kbd> = left, <kbd>J</kbd> = right</li>
           <li><strong>Clues:</strong> the arrow points to the object the aliens prefer more.</li>
           <li><strong>Position:</strong> the preferred object is always on top of the pair.</li>
           <li>Sometimes, <strong>multiple clues</strong> can be relevant to a question.</li>
           <li><strong>Feedback:</strong> Available during learning, not during the test phase.</li>
           <li><strong>Time limit:</strong> Answer promptly — trials end if you're too slow.</li>
           ${extraBullets.join('\n           ')}
         </ul>
       </div>
       ${helpReminderHTML()}
       <p>When you're ready, proceed to begin the learning phase.</p>`
    ),
  ];
}


// --- Before the tests ---

/**
 * The seven pages between the learning phase and the first test: the learning phase is over;
 * test feedback does not say whether an answer was correct; it outlines the chosen object
 * (pages 3-5 show it, with two of the query-only practice items); its timing is fixed; be fast
 * and accurate; a summary.
 *
 * @returns {string[]}
 */
export function buildTransitionPages() {
  const items = stimuliState.queryOnlyPracticeItems;
  const qLeft = items[0].id;
  const qRight = items[1].id;
  const labelHigh = formatLabel(items[0].label);
  const labelLow  = formatLabel(items[1].label);

  // The test feedback, as on a test trial.
  const neutralPanelHTML = `
    <div class="feedback-relation">
      You chose <strong>${labelHigh}</strong> over <strong>${labelLow}</strong>.
    </div>
    <div class="feedback-continue">Press <kbd>Space</kbd> to continue.</div>`;

  const neutralDisplay = buildInstructionDisplay({
    queryLeft: qLeft, queryRight: qRight,
    showPairRow: false,
    showKeyHints: true,
    selectedSide: 'left', isNeutral: true,
    feedbackHTML: neutralPanelHTML,
  });

  // The wait before Space works on test trials, in words ("1 second").
  const neutralMs = framesToMs(CONFIG.timing.feedbackNeutralFrames);
  const neutralSec = (neutralMs / 1000).toFixed(neutralMs % 1000 === 0 ? 0 : 1);
  const neutralLabel = `${neutralSec} ${neutralSec === '1' ? 'second' : 'seconds'}`;

  // The summary of page 7.
  const bullets = [];
  bullets.push('You will <strong>NOT</strong> be told whether your answer is correct.');
  bullets.push('Instead, your chosen object will be <strong>highlighted in black</strong>.');
  bullets.push('You may see <strong>new images</strong> that you haven\'t seen before.');
  bullets.push('The objects in the clues may be replaced with <strong>gray boxes</strong> on some trials.');
  bullets.push('The feedback timing is <strong>the same on every trial</strong>.');
  bullets.push('Your performance on the test determines your <strong>bonus payment</strong> — try your best!');
  bullets.push('Your points will be <strong>hidden</strong> during the test phase, but still tracked.');
  bullets.push('Try to be <strong>fast</strong> and <strong>accurate</strong>.');
  const reminderBox = `
        <div class="summary-box">
          <p><strong>Keep in mind:</strong></p>
          <ul>
            ${bullets.map(b => `<li>${b}</li>`).join('\n            ')}
          </ul>
        </div>`;

  return [
    // Page 1: the learning phase is over.
    instructionPage(`
      <h2>Great work!</h2>
      <p>You've completed the learning phase.</p>
      <p>Next, you'll be tested on what you've learned.</p>`),

    // Page 2: no correct/incorrect feedback.
    instructionPage(`
      <p>The feedback in the test is different.</p>
      <p>You will <strong>NOT</strong> be told whether your answer is correct.</p>`),

    // Page 3: the chosen object is outlined.
    instructionPage(
      `<p>Instead, after you respond, your chosen object will be
       highlighted in <strong>black</strong>.</p>`,
      neutralDisplay
    ),

    // Page 4: the wait.
    instructionPage(
      `<p>The feedback timing will also change. You will have to wait
       about <strong>${neutralLabel}</strong> before you can continue.</p>`,
      neutralDisplay
    ),

    // Page 5: the same wait after every answer.
    instructionPage(
      `<p>The delay before you can continue will be
       <strong>exactly the same</strong> whether you got it correct or
       incorrect.</p>`,
      neutralDisplay
    ),

    // Page 6: fast and accurate.
    instructionPage(`
      <p>Try to be as <strong>fast</strong> and as
      <strong>accurate</strong> as possible.</p>
      <p>Remember, your <strong>bonus payment</strong> depends on your performance during the test.</p>`),

    // Page 7: the summary.
    instructionPage(`
      ${reminderBox}
      ${helpReminderHTML()}
      <p>When you're ready, click <strong>Next</strong> to begin the test phase.</p>`),
  ];
}
