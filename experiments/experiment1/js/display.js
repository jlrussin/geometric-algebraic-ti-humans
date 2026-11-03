/**
 * The task display and its jsPsych plugin.
 *
 * The display shows the query (left image, "?", right image) above a row of pairs, the clues.
 * Each pair stacks two images, the preferred one on top, joined by an arrow that points up to
 * it. Key hints, or after a response the feedback, sit below the query. A masked pair shows
 * gray boxes in place of the images.
 *
 * Sizes are set in CONFIG.display as pixels at the smallest supported window (1024 x 700, where
 * the display is 983 px wide) and converted to container-width units (cqw), so the display
 * scales with the window. They reach the stylesheet as CSS custom properties.
 *
 * @module display
 */

import { CONFIG, framesToMs } from './config.js';
import { getStimulusById, ALL_IMAGES } from './stimuli.js';
import { formatLabel } from './utils.js';

// --- Sizing ---

/** Width of the display at the smallest supported window (96vw of 1024 px). */
const REFERENCE_CONTAINER_WIDTH_PX = 983;

const pxToCqw = (px) => (px / REFERENCE_CONTAINER_WIDTH_PX) * 100;

/**
 * The style attribute of a display: its width and the sizes as CSS custom properties. The
 * instruction pages use a narrower display, also capped by the window height.
 */
function buildDisplayStyle({ instruction = false } = {}) {
  const widthVw = instruction
    ? CONFIG.display.instructionMaxWidthVw
    : CONFIG.display.maxWidthVw;
  const widthPx = instruction
    ? CONFIG.display.instructionMaxWidthPx
    : CONFIG.display.maxWidthPx;
  const widthVh = instruction ? CONFIG.display.instructionMaxWidthVh : null;

  const vars = {
    '--ll-image-size': `${pxToCqw(CONFIG.display.imageSizePx)}cqw`,
    '--ll-pair-connector-height': `${pxToCqw(CONFIG.display.pairConnectorHeightPx)}cqw`,
    '--ll-pair-arrow-image-gap': `${pxToCqw(CONFIG.display.pairArrowImageGapPx)}cqw`,
    '--ll-pair-arrow-head-height': `${pxToCqw(CONFIG.display.pairArrowHeadHeightPx)}cqw`,
    '--ll-pair-arrow-cap-width': `${pxToCqw(CONFIG.display.pairArrowCapWidthPx)}cqw`,
    '--ll-pair-arrow-shaft-width': `${pxToCqw(CONFIG.display.pairArrowShaftWidthPx)}cqw`,
    '--ll-pair-row-gap': `${pxToCqw(CONFIG.display.pairRowGapPx)}cqw`,
    '--ll-pair-to-query-gap': `${pxToCqw(instruction
      ? CONFIG.display.instructionPairToQueryGapPx
      : CONFIG.display.pairToQueryGapPx)}cqw`,
    '--ll-query-image-gap': `${pxToCqw(CONFIG.display.queryImageGapPx)}cqw`,
    '--ll-response-slot-height': `${pxToCqw(CONFIG.display.responseSlotHeightPx)}cqw`,
    '--ll-gray-box-fill': CONFIG.display.grayBoxFill,
    '--ll-gray-box-border-width': `${pxToCqw(CONFIG.display.grayBoxBorderPx)}cqw`,
  };
  const varStr = Object.entries(vars).map(([k, v]) => `${k}: ${v}`).join('; ');
  const widthTerms = [`${widthVw}vw`, `${widthPx}px`];
  if (widthVh != null) widthTerms.push(`${widthVh}vh`);
  return `width: min(${widthTerms.join(', ')}); ${varStr};`;
}

// --- Image preload ---

/**
 * Load every image once before the first screen, so that trials draw them from the browser
 * cache, and fill the loading bar of index.html. A session goes on when some images fail, but
 * stops when none loads (the images have not been downloaded).
 * @returns {Promise<{durationMs: number, loaded: number, failed: number}>}
 */
export async function preloadImages() {
  const toLoad = ALL_IMAGES;
  const total = toLoad.length;
  let completed = 0;
  let failed = 0;

  const progressBar = document.getElementById('loading-progress-bar');
  const progressText = document.getElementById('loading-progress-text');

  function updateProgress() {
    const pct = total > 0 ? Math.round((completed / total) * 100) : 100;
    if (progressBar) progressBar.style.width = pct + '%';
    if (progressText) progressText.textContent = `${pct}%`;
  }

  updateProgress();
  const startTime = performance.now();

  const promises = toLoad.map(s => new Promise((resolve) => {
    const img = new Image();
    img.onload = () => { completed++; updateProgress(); resolve(); };
    img.onerror = () => { console.warn(`Failed to load: ${s.image}`); completed++; failed++; updateProgress(); resolve(); };
    img.src = s.image;
  }));
  await Promise.all(promises);

  if (total > 0 && failed === total) {
    throw new Error('None of the images could be loaded from media/pps/. Run '
      + '`uv run geo-alg-ti-humans images` from the repository root, then reload this page.');
  }

  const durationMs = Math.round(performance.now() - startTime);
  return { durationMs, loaded: completed - failed, failed };
}

// --- HTML ---

/**
 * An image of the query or of a pair (both have the same size).
 *
 * @param {string} itemId
 * @param {string} cssClass - "ll-pair-image" or "ll-query-image" (with modifiers).
 * @returns {string} HTML
 */
export function renderItem(itemId, cssClass) {
  const stim = getStimulusById(itemId);
  return `<img src="${stim.image}" class="${cssClass}" alt="${formatLabel(stim.label)}" draggable="false">`;
}

/**
 * The connector of a pair: a vertical arrow, drawn as an inline SVG, whose head points up to the
 * preferred object. The viewBox uses pixel-equivalent units (cap width x connector height) so
 * the shapes keep their proportions when the SVG is stretched to its box.
 *
 * @returns {string} HTML
 */
function renderConnector() {
  const W = CONFIG.display.pairArrowCapWidthPx;
  const H = CONFIG.display.pairConnectorHeightPx;
  const SHAFT_HALF_W = CONFIG.display.pairArrowShaftWidthPx / 2;
  const HEAD_HEIGHT = CONFIG.display.pairArrowHeadHeightPx;
  const HEAD_HALF_W = W / 2;
  const cx = W / 2;

  // The shaft has rounded ends; its top end starts inside the arrowhead so the rounding is
  // hidden, and its bottom end is the bottom of the box.
  const shaftTop = HEAD_HEIGHT - SHAFT_HALF_W;
  const shaftRect = `<rect x="${cx - SHAFT_HALF_W}" y="${shaftTop}"
                            width="${SHAFT_HALF_W * 2}" height="${H - shaftTop}"
                            rx="${SHAFT_HALF_W}" ry="${SHAFT_HALF_W}"
                            fill="currentColor" />`;
  // The arrowhead: an isosceles triangle with its point at the top.
  const head = `<polygon points="${cx - HEAD_HALF_W},${HEAD_HEIGHT} ${cx + HEAD_HALF_W},${HEAD_HEIGHT} ${cx},0"
                            fill="currentColor" />`;

  return `
    <div class="ll-pair-connector ll-pair-connector--arrow">
      <svg class="ll-pair-arrow" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
        ${shaftRect}
        ${head}
      </svg>
    </div>`;
}

/**
 * One pair: top image, arrow, bottom image. On instruction pages a pair can be dimmed (with an
 * explicit opacity) or highlighted.
 *
 * @param {object} slot - A slot of utils.assignSlotsToLinks; `maskItem` shows gray boxes.
 * @param {object} [opts]
 * @param {boolean} [opts.dimmed=false]
 * @param {boolean} [opts.highlighted=false]
 * @param {?number} [opts.dimOpacity=null]
 * @returns {string} HTML
 */
function renderPair(slot, { dimmed = false, highlighted = false, dimOpacity = null } = {}) {
  const stateClasses = [
    dimmed ? 'll-pair--dimmed' : '',
    highlighted ? 'll-pair--highlighted' : '',
  ].filter(Boolean).join(' ');
  const cls = stateClasses ? `ll-pair ${stateClasses}` : 'll-pair';
  const styleAttr = (dimmed && dimOpacity != null) ? ` style="opacity: ${dimOpacity}"` : '';
  const topHTML = slot.maskItem
    ? `<div class="ll-pair-image ll-pair-image--masked" aria-hidden="true"></div>`
    : renderItem(slot.topItem, 'll-pair-image');
  const bottomHTML = slot.maskItem
    ? `<div class="ll-pair-image ll-pair-image--masked" aria-hidden="true"></div>`
    : renderItem(slot.bottomItem, 'll-pair-image');
  return `
    <div class="${cls}" data-pair-index="${slot.pairIndex}"${styleAttr}>
      ${topHTML}
      ${renderConnector()}
      ${bottomHTML}
    </div>`;
}

/**
 * The pair row, in the order of the pair indices. On instruction pages the row can be faded
 * (opacity) or, with highlightSlots, show some pairs at full opacity and dim the rest; the
 * dimming is set on each pair, since an opacity on the row would also fade the highlighted
 * pairs.
 *
 * @param {Array<object>} slots
 * @param {object} [opts]
 * @param {number} [opts.opacity=1]
 * @param {?number[]} [opts.highlightSlots=null] - Pair indices shown at full opacity.
 * @returns {string} HTML
 */
function renderPairRow(slots, { opacity = 1, highlightSlots = null } = {}) {
  const sorted = [...slots].sort((a, b) => a.pairIndex - b.pairIndex);
  const useHighlight = Array.isArray(highlightSlots) && highlightSlots.length > 0;

  const dimOpacity = (opacity != null && opacity < 1) ? opacity : 0.5;
  const rowStyleAttr = (!useHighlight && opacity < 1)
    ? ` style="opacity: ${opacity}"` : '';
  const pairsHTML = sorted.map(slot => {
    if (useHighlight) {
      const hi = highlightSlots.includes(slot.pairIndex);
      return renderPair(slot, {
        dimmed: !hi,
        highlighted: hi,
        dimOpacity: hi ? null : dimOpacity,
      });
    }
    return renderPair(slot);
  }).join('');
  return `<div class="ll-pair-row"${rowStyleAttr}>${pairsHTML}</div>`;
}

/**
 * The query of an instruction page: the two images, and below them either the key hints or a
 * feedback box (one slot holds both, so the layout does not move). Options as in
 * buildInstructionDisplay().
 */
function renderQueryArea({
  queryLeft, queryRight,
  showKeyHints = true,
  keyHintsOpacity = 1,
  selectedSide = null, selectedCorrect = true, isNeutral = false,
  leftHighlight = null, rightHighlight = null,
  feedbackHTML = '', feedbackBorderColor = null,
}) {
  const selectedClass = isNeutral
    ? ' selected-neutral'
    : (selectedCorrect ? ' selected-correct' : ' selected-incorrect');
  const leftClass = leftHighlight === 'correct'
    ? ' selected-correct'
    : leftHighlight === 'incorrect'
      ? ' selected-incorrect'
      : (selectedSide === 'left' ? selectedClass : '');
  const rightClass = rightHighlight === 'correct'
    ? ' selected-correct'
    : rightHighlight === 'incorrect'
      ? ' selected-incorrect'
      : (selectedSide === 'right' ? selectedClass : '');

  const hintContainerStyle = feedbackHTML ? ' style="visibility: hidden"' : '';
  const hintChildStyle = !feedbackHTML && keyHintsOpacity < 1
    ? ` style="opacity: ${keyHintsOpacity}"` : '';
  const keyHintsHTML = showKeyHints ? `
    <div class="ll-key-hints"${hintContainerStyle}>
      <span class="ll-key-hint ll-key-hint--left"${hintChildStyle}><kbd>F</kbd> Left</span>
      <span class="ll-key-hint ll-key-hint--right"${hintChildStyle}><kbd>J</kbd> Right</span>
    </div>` : '';

  const feedbackBorderStyle = feedbackBorderColor
    ? ` style="border-color: ${feedbackBorderColor}"` : '';
  const feedbackAreaClasses = isNeutral
    ? 'll-feedback-area ll-feedback-area--visible ll-feedback-area--neutral'
    : 'll-feedback-area ll-feedback-area--visible';
  const feedbackAreaHTML = feedbackHTML
    ? `<div class="${feedbackAreaClasses}"${feedbackBorderStyle}>${feedbackHTML}</div>`
    : '<div class="ll-feedback-area"></div>';

  return `
    <div class="ll-query-area">
      <div class="ll-query-block">
        <div class="ll-query-row">
          ${renderItem(queryLeft, 'll-query-image' + leftClass)}
          <span class="ll-query-separator">?</span>
          ${renderItem(queryRight, 'll-query-image' + rightClass)}
        </div>
        <div class="ll-response-slot">
          ${keyHintsHTML}
          ${feedbackAreaHTML}
        </div>
      </div>
    </div>`;
}

// --- Instruction pages ---

/**
 * A static display for an instruction page, laid out like a trial (query above the pair row).
 *
 * Options:
 *   - slots: the pairs; showPairRow false leaves the row empty but keeps its height, so the
 *     query stays in place from page to page.
 *   - pairRowOpacity (0 to 1): fade the pair row; highlightSlots: pair indices shown at full
 *     opacity while the others are dimmed to pairRowOpacity.
 *   - showKeyHints, keyHintsOpacity (0 to 1): the F / J hints.
 *   - selectedSide ('left', 'right' or null) and selectedCorrect: outline the chosen image in
 *     green or red; isNeutral: the dark outline and feedback box of the tests instead.
 *   - leftHighlight, rightHighlight ('correct', 'incorrect' or null): outline one image
 *     regardless of the choice (the timeout feedback).
 *   - feedbackHTML: a feedback box in place of the key hints; feedbackBorderColor: its border.
 *
 * @param {object} params
 * @returns {string} HTML
 */
export function buildInstructionDisplay(params) {
  const {
    slots = [], queryLeft, queryRight,
    showPairRow = true, showKeyHints = true,
    pairRowOpacity = 1, keyHintsOpacity = 1,
    highlightSlots = null,
    selectedSide = null, selectedCorrect = true, isNeutral = false,
    leftHighlight = null, rightHighlight = null,
    feedbackHTML = '', feedbackBorderColor = null,
  } = params;

  const pairRowVisible = showPairRow && Array.isArray(slots) && slots.length > 0;
  const pairRowInner = pairRowVisible
    ? renderPairRow(slots, { opacity: pairRowOpacity, highlightSlots })
    : '';
  const pairWrapClass = pairRowVisible
    ? 'll-pair-row-wrap'
    : 'll-pair-row-wrap ll-pair-row-wrap--reserved';

  const queryHTML = renderQueryArea({
    queryLeft, queryRight,
    showKeyHints,
    keyHintsOpacity,
    selectedSide, selectedCorrect, isNeutral,
    leftHighlight, rightHighlight,
    feedbackHTML, feedbackBorderColor,
  });

  return `
    <div class="ll-display ll-display--instruction" style="${buildDisplayStyle({ instruction: true })}">
      ${queryHTML}
      <div class="${pairWrapClass}">${pairRowInner}</div>
    </div>`;
}

// --- The jsPsych plugin ---

/**
 * A task trial: fixation, then the query and the pair row together; a response with F or J (or
 * none before the deadline); then feedback, dismissed with Space after a minimum time or ended
 * by a deadline. Practice and learning trials give correct/incorrect feedback; test trials
 * only outline the chosen image ("You chose X over Y."). The saved row holds the trial's
 * parameters and the response.
 */
export class LinkedListDisplayPlugin {

  static info = {
    name: 'linked-list-display',
    version: '2.0.0',
    parameters: {
      query_left:           { type: jsPsychModule.ParameterType.STRING,  default: undefined },
      query_right:          { type: jsPsychModule.ParameterType.STRING,  default: undefined },
      correct_side:         { type: jsPsychModule.ParameterType.STRING,  default: undefined },
      slots:                { type: jsPsychModule.ParameterType.OBJECT,  default: [] },
      fixation_duration:    { type: jsPsychModule.ParameterType.INT,     default: framesToMs(CONFIG.timing.fixationFrames) },
      response_deadline:    { type: jsPsychModule.ParameterType.INT,     default: null },
      show_feedback:        { type: jsPsychModule.ParameterType.BOOL,    default: false },
      // Test feedback: the chosen image is outlined in dark gray, without correct/incorrect
      // (ignored when show_feedback is true).
      show_neutral_feedback: { type: jsPsychModule.ParameterType.BOOL,    default: false },
      query_left_rank:      { type: jsPsychModule.ParameterType.INT,     default: null },
      query_right_rank:     { type: jsPsychModule.ParameterType.INT,     default: null },
      ordinal_distance:     { type: jsPsychModule.ParameterType.INT,     default: null },
      context_hops:         { type: jsPsychModule.ParameterType.INT,     default: null },
      num_context_pairs:    { type: jsPsychModule.ParameterType.INT,     default: null },
      icl_consistent_side:  { type: jsPsychModule.ParameterType.STRING,  default: null },
      phase:                { type: jsPsychModule.ParameterType.STRING,  default: '' },
      icl_ordering:         { type: jsPsychModule.ParameterType.INT,     default: null },
      context_display:      { type: jsPsychModule.ParameterType.STRING,  default: 'shown' },
      chain_order_json:     { type: jsPsychModule.ParameterType.STRING,  default: '' },
      inserted_distractor_positions_json:    { type: jsPsychModule.ParameterType.STRING, default: '' },
      inserted_distractor_ids_json:          { type: jsPsychModule.ParameterType.STRING, default: '' },
      inserted_distractor_rank_buckets_json: { type: jsPsychModule.ParameterType.STRING, default: '' },
      swap_distractor_id:          { type: jsPsychModule.ParameterType.STRING, default: null },
      swap_distractor_rank_bucket: { type: jsPsychModule.ParameterType.STRING, default: null },
      swapped_item_id:             { type: jsPsychModule.ParameterType.STRING, default: null },
      on_feedback:          { type: jsPsychModule.ParameterType.FUNCTION, default: null },
    },
  };

  constructor(jsPsych) { this.jsPsych = jsPsych; }

  trial(display_element, trial) {
    let queryOnsetTime = null;
    let responseAllowed = false;
    let feedbackReady = false;
    let feedbackVisibleTime = null;
    let finished = false;
    let pendingData = null;

    const removeListeners = () => {
      document.removeEventListener('keydown', handleKeypress);
      document.removeEventListener('keydown', handleFeedbackKey);
    };

    const finish = (data) => {
      if (finished) return;
      finished = true;
      removeListeners();
      this.jsPsych.pluginAPI.clearAllTimeouts();
      display_element.innerHTML = '';
      this.jsPsych.finishTrial(data);
    };

    // The distractors shown on this trial: the two in the chain (the end distractors in the ICL
    // test and in practice) and, on learning trials, the one that replaced a main item.
    const insertedIds = trial.inserted_distractor_ids_json
      ? JSON.parse(trial.inserted_distractor_ids_json) : [];
    const distractorSet = new Set(insertedIds);
    if (trial.swap_distractor_id) distractorSet.add(trial.swap_distractor_id);

    const collectData = (response, rt, responseKey = null) => ({
      rt: rt !== null ? Math.round(rt) : null,
      response,
      response_key: responseKey,
      is_correct: response === trial.correct_side,
      query_left: trial.query_left,
      query_right: trial.query_right,
      query_left_rank: trial.query_left_rank,
      query_right_rank: trial.query_right_rank,
      ordinal_distance: trial.ordinal_distance,
      context_hops: trial.context_hops,
      num_context_pairs: trial.num_context_pairs,
      icl_consistent_side: trial.icl_consistent_side,
      is_icl_consistent: trial.phase === 'test_arbitrage'
        ? response === trial.icl_consistent_side : null,
      is_iwl_consistent: trial.phase === 'test_arbitrage'
        ? response === trial.correct_side : null,
      phase: trial.phase,
      icl_ordering: trial.icl_ordering,
      context_display: trial.context_display,
      chain_order_json: trial.chain_order_json,
      inserted_distractor_positions_json: trial.inserted_distractor_positions_json,
      inserted_distractor_ids_json: trial.inserted_distractor_ids_json,
      inserted_distractor_rank_buckets_json: trial.inserted_distractor_rank_buckets_json,
      swap_distractor_id: trial.swap_distractor_id,
      swap_distractor_rank_bucket: trial.swap_distractor_rank_bucket,
      swapped_item_id: trial.swapped_item_id,
      // One entry per link of the chain, from its top; pair_index 0 is the leftmost pair.
      slot_assignment_json: JSON.stringify(trial.slots.map(s => ({
        pair_index: s.pairIndex,
        top_item: s.topItem,
        bottom_item: s.bottomItem,
        top_is_higher: s.topIsHigher,
        top_is_distractor: distractorSet.has(s.topItem),
        bottom_is_distractor: distractorSet.has(s.bottomItem),
      }))),
      query_onset_time_ms: queryOnsetTime,
      is_timed_out: response === null,
      is_feedback_timed_out: null,
      feedback_dismiss_rt_ms: null,
      window_width_px: window.innerWidth,
      window_height_px: window.innerHeight,
      screen_width_px: screen.width,
      screen_height_px: screen.height,
      device_pixel_ratio: window.devicePixelRatio,
    });

    // The trial screen. The pair row's place is kept when there is no row (query-only
    // practice), so the query is always in the same place.
    const buildDisplay = () => {
      const noSlots = !Array.isArray(trial.slots) || trial.slots.length === 0;
      const pairsHTML = noSlots ? '' : renderPairRow(trial.slots);
      const pairWrapClass = noSlots
        ? 'll-pair-row-wrap ll-pair-row-wrap--reserved'
        : 'll-pair-row-wrap';

      display_element.innerHTML = `
        <div class="ll-display" style="${buildDisplayStyle()}">
          <div class="ll-query-area">
            <div class="ll-query-block">
              <div class="ll-query-row">
                ${renderItem(trial.query_left, 'll-query-image')}
                <span class="ll-query-separator">?</span>
                ${renderItem(trial.query_right, 'll-query-image')}
              </div>
              <div class="ll-response-slot">
                <div class="ll-key-hints">
                  <span class="ll-key-hint ll-key-hint--left"><kbd>F</kbd> Left</span>
                  <span class="ll-key-hint ll-key-hint--right"><kbd>J</kbd> Right</span>
                </div>
                <div class="ll-feedback-area"></div>
              </div>
            </div>
          </div>
          <div class="${pairWrapClass}">${pairsHTML}</div>
        </div>`;
    };

    // Fixation: the whole trial screen, hidden, under a "+", so that nothing moves when the
    // query appears.
    const showFixation = () => {
      const noSlots = !Array.isArray(trial.slots) || trial.slots.length === 0;
      const pairsHTML = noSlots ? '' : renderPairRow(trial.slots);
      const pairWrapClass = noSlots
        ? 'll-pair-row-wrap ll-pair-row-wrap--reserved'
        : 'll-pair-row-wrap';
      display_element.innerHTML = `
        <div class="ll-display ll-display--fixating" style="${buildDisplayStyle()}">
          <div class="ll-query-area">
            <div class="ll-query-block">
              <div class="ll-query-row">
                ${renderItem(trial.query_left, 'll-query-image')}
                <span class="ll-query-separator">?</span>
                ${renderItem(trial.query_right, 'll-query-image')}
              </div>
              <div class="ll-response-slot">
                <div class="ll-key-hints">
                  <span class="ll-key-hint ll-key-hint--left"><kbd>F</kbd> Left</span>
                  <span class="ll-key-hint ll-key-hint--right"><kbd>J</kbd> Right</span>
                </div>
                <div class="ll-feedback-area"></div>
              </div>
            </div>
          </div>
          <div class="${pairWrapClass}">${pairsHTML}</div>
          <div class="ll-fixation-overlay">+</div>
        </div>`;
      if (trial.fixation_duration > 0) {
        this.jsPsych.pluginAPI.setTimeout(showQuery, trial.fixation_duration);
      } else {
        showQuery();
      }
    };

    const showQuery = () => {
      buildDisplay();
      queryOnsetTime = performance.now();
      responseAllowed = true;
      if (trial.response_deadline) {
        this.jsPsych.pluginAPI.setTimeout(() => {
          if (responseAllowed) endResponse(null);
        }, trial.response_deadline);
      }
    };

    const endResponse = (response, rt = null, responseKey = null) => {
      responseAllowed = false;
      const data = collectData(response, rt, responseKey);
      if (trial.show_feedback) showFeedback(data, 'full');
      else if (trial.show_neutral_feedback) showFeedback(data, 'neutral');
      else finish(data);
    };

    // Feedback.
    //   'full' (practice, learning): the chosen image outlined in green or red (a timeout
    //     outlines both), "Correct!", "Incorrect." or "Too slow!", and the relation of the two
    //     items. Space works after feedbackCorrectFrames or feedbackIncorrectFrames.
    //   'neutral' (tests): the chosen image outlined in dark gray and "You chose X over Y."
    //     ("Too slow!" after a timeout, with no outline). Space works after
    //     feedbackNeutralFrames.
    // Once Space works, the trial also ends by itself after feedbackContinueDeadlineMs.
    const showFeedback = (data, mode = 'full') => {
      const isNeutral = mode === 'neutral';
      const isCorrect = data.is_correct;
      const isTimeout = data.response === null;
      const higherItem = trial.correct_side === 'left' ? trial.query_left : trial.query_right;
      const lowerItem  = trial.correct_side === 'left' ? trial.query_right : trial.query_left;
      const hLabel = formatLabel(getStimulusById(higherItem)?.label || higherItem);
      const lLabel = formatLabel(getStimulusById(lowerItem)?.label || lowerItem);

      if (trial.on_feedback) trial.on_feedback(data);

      const queryImages = display_element.querySelectorAll('.ll-query-image');
      if (isNeutral) {
        if (data.response) {
          const chosenImg = data.response === 'left' ? queryImages[0] : queryImages[1];
          if (chosenImg) chosenImg.classList.add('selected-neutral');
        }
      } else if (isTimeout) {
        const correctImg = trial.correct_side === 'left' ? queryImages[0] : queryImages[1];
        const incorrectImg = trial.correct_side === 'left' ? queryImages[1] : queryImages[0];
        if (correctImg) correctImg.classList.add('selected-correct');
        if (incorrectImg) incorrectImg.classList.add('selected-incorrect');
      } else if (data.response) {
        const chosenImg = data.response === 'left' ? queryImages[0] : queryImages[1];
        if (chosenImg) {
          chosenImg.classList.add(isCorrect ? 'selected-correct' : 'selected-incorrect');
        }
      }

      // The feedback takes the place of the key hints.
      const hints = display_element.querySelector('.ll-key-hints');
      if (hints) hints.style.visibility = 'hidden';

      const el = display_element.querySelector('.ll-feedback-area');
      if (isNeutral) {
        el.classList.add('ll-feedback-area--visible', 'll-feedback-area--neutral');
        if (isTimeout) {
          el.innerHTML = `
            <div class="feedback-text feedback-neutral">Too slow!</div>
            <div class="feedback-continue" style="visibility:hidden">
              Press <kbd>Space</kbd> to continue.
            </div>`;
        } else {
          const chosenItem = data.response === 'left' ? trial.query_left : trial.query_right;
          const otherItem  = data.response === 'left' ? trial.query_right : trial.query_left;
          const cLabel = formatLabel(getStimulusById(chosenItem)?.label || chosenItem);
          const oLabel = formatLabel(getStimulusById(otherItem)?.label || otherItem);
          el.innerHTML = `
            <div class="feedback-relation">
              You chose <strong>${cLabel}</strong> over <strong>${oLabel}</strong>.
            </div>
            <div class="feedback-continue" style="visibility:hidden">
              Press <kbd>Space</kbd> to continue.
            </div>`;
        }
      } else {
        const headerClass = isCorrect ? 'feedback-correct' : 'feedback-incorrect';
        const headerText = isTimeout ? 'Too slow!' : (isCorrect ? 'Correct!' : 'Incorrect.');
        const borderClass = isCorrect ? 'll-feedback-area--correct' : 'll-feedback-area--incorrect';
        el.classList.add('ll-feedback-area--visible', borderClass);
        el.innerHTML = `
          <div class="feedback-text ${headerClass}">${headerText}</div>
          <div class="feedback-relation">
            The aliens prefer <strong>${hLabel}</strong> over <strong>${lLabel}</strong>.
          </div>
          <div class="feedback-continue" style="visibility:hidden">
            Press <kbd>Space</kbd> to continue.
          </div>`;
      }

      const minDur = isNeutral
        ? framesToMs(CONFIG.timing.feedbackNeutralFrames)
        : isCorrect
          ? framesToMs(CONFIG.timing.feedbackCorrectFrames)
          : framesToMs(CONFIG.timing.feedbackIncorrectFrames);

      this.jsPsych.pluginAPI.setTimeout(() => {
        el.querySelector('.feedback-continue').style.visibility = 'visible';
        feedbackReady = true;
        feedbackVisibleTime = performance.now();
        this.jsPsych.pluginAPI.setTimeout(() => {
          if (!feedbackReady || finished) return;
          pendingData.is_feedback_timed_out = true;
          pendingData.feedback_dismiss_rt_ms = Math.round(performance.now() - feedbackVisibleTime);
          finish(pendingData);
        }, CONFIG.timing.feedbackContinueDeadlineMs);
      }, minDur);

      pendingData = data;
      document.addEventListener('keydown', handleFeedbackKey);
    };

    const handleFeedbackKey = (e) => {
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
      if (e.key === ' ' && feedbackReady) {
        pendingData.is_feedback_timed_out = false;
        pendingData.feedback_dismiss_rt_ms = Math.round(performance.now() - feedbackVisibleTime);
        finish(pendingData);
      }
    };

    const handleKeypress = (e) => {
      if (!responseAllowed) return;
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
      const key = e.key.toLowerCase();
      if (key !== CONFIG.responseKeys.left && key !== CONFIG.responseKeys.right) return;
      responseAllowed = false;
      endResponse(
        key === CONFIG.responseKeys.left ? 'left' : 'right',
        performance.now() - queryOnsetTime,
        key,
      );
    };

    document.addEventListener('keydown', handleKeypress);
    showFixation();
  }
}
