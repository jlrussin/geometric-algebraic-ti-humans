/**
 * QuestionTrialPlugin (`question-trial`): one question screen.
 *
 * The plugin receives display strings only: the question (HTML from js/copy.js), the two answer
 * labels, the statements in screen order, and two durations. The question's design fields travel
 * in the node's `data` object, which jsPsych merges into the saved row; this plugin never reads
 * them, and its result adds only the response and the page fields. Scoring happens in the
 * node's on_finish (trial-logic's scoreResponse), never here.
 *
 * Sequence:
 *   1. Build the DOM with the question, answers and statements hidden (`visibility`, never
 *      `display`), so the layout is final before anything shows.
 *   2. Reveal them in one frame; stamp onset on the second requestAnimationFrame after the
 *      reveal (the first frame callback runs before the reveal is painted, the second after
 *      it).
 *   3. Enable F/J and start the deadline.
 *   4. On an answer: lock input, outline the chosen answer, write message line 1 ("You chose
 *      ..."). On a timeout: line 1 is the timeout text and line 2 shows at once.
 *   5. After `confirmation_min_ms`, show line 2 ("Press space to continue.") and accept Space.
 *   6. Space finishes the trial. There is no automatic advance.
 *
 * Keys: a document listener in the capturing phase, so focus never matters. `event.code`
 * KeyF = left, KeyJ = right. Auto-repeat keydowns (`event.repeat`) are ignored: a key already
 * down at onset sends only auto-repeats, so it counts only once it is released and pressed again
 * (a fresh keydown is itself proof of the release, even if the keyup was missed). F/J with Ctrl,
 * Cmd or Alt held is not an answer. Other keys during the answer window (and F/J with those
 * modifiers) are counted (`invalid_key_count`). Space is always preventDefault-ed. Copy, cut,
 * the context menu, selection and drag are blocked; copy, cut and context-menu attempts are
 * counted (`copy_attempt_count`), and Ctrl/Cmd + C/A/F/G/P/S/U, F3 and "/" are blocked and
 * counted (`blocked_shortcut_count`).
 *
 * If jsPsych empties the display element before the trial ends, every handler finds that this
 * trial's frame is no longer in the document and removes its listeners, so nothing leaks into
 * the next screen.
 *
 * @module question-trial-plugin
 */

import { CONFIG } from './config.js';
import { continuePrompt, confirmation, timeoutMessage } from './copy.js';

const { ParameterType } = window.jsPsychModule;

const RESPONSE_CODES = { KeyF: 'left', KeyJ: 'right' };

const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Fn', 'OS']);
const BLOCKED_LETTERS = new Set(['c', 'a', 'f', 'g', 'p', 's', 'u']);

/**
 * True for the blocked find, copy, print, save and view-source shortcuts (Ctrl/Cmd +
 * C/A/F/G/P/S/U, F3, "/"). The one definition: js/experiment.js blocks the same keys on the
 * other screens.
 * @param {KeyboardEvent} e
 * @returns {boolean}
 */
export function isBlockedShortcut(e) {
  const key = (e.key || '').toLowerCase();
  if ((e.ctrlKey || e.metaKey) && BLOCKED_LETTERS.has(key)) return true;
  return e.key === 'F3' || e.key === '/';
}

/**
 * Stage scale actually in use: the rendered frame width over its 1024-px
 * design width (the CSS `--u`).
 * @param {HTMLElement} frameEl
 * @returns {number}
 */
function measureStageScale(frameEl) {
  const width = frameEl.getBoundingClientRect().width;
  return Math.round((width / 1024) * 10000) / 10000;
}

/**
 * An event's time in the performance.now() timebase. Every supported browser
 * stamps `event.timeStamp` that way; the fallback guards an engine that
 * does not (an epoch time would dwarf performance.now()). The one
 * definition: js/continue-screen-plugin.js uses it too.
 * @param {Event} e
 * @returns {number}
 */
export function eventTime(e) {
  const now = performance.now();
  return (e.timeStamp > 0 && e.timeStamp <= now + 1000) ? e.timeStamp : now;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * One answer: a fixed slot (`.q-answer.is-left|.is-right`) holding the unit that the chosen
 * outline wraps: the label with its key cap centered below. The placement is this helper plus
 * the answer rules in styles/experiment.css.
 * @param {'left'|'right'} side
 * @param {string} label - Plain text.
 * @returns {HTMLElement}
 */
function answerSlot(side, label) {
  const slot = el('div', `q-answer is-${side}`);
  const unit = el('div', 'q-answer-unit');
  unit.append(el('span', 'q-label', label), el('span', 'keycap', side === 'left' ? 'F' : 'J'));
  slot.append(unit);
  return slot;
}

class QuestionTrialPlugin {
  static info = {
    name: 'question-trial',
    version: '1.0.0',
    parameters: {
      /** The question at the top, as HTML from js/copy.js. */
      question_html: { type: ParameterType.HTML_STRING, default: undefined },
      /** Answer label shown at F (plain text). */
      left_label: { type: ParameterType.STRING, default: undefined },
      /** Answer label shown at J (plain text). */
      right_label: { type: ParameterType.STRING, default: undefined },
      /** Statements in screen order (plain text), one per line. */
      statements: { type: ParameterType.STRING, array: true, default: undefined },
      /** Answer window from onset, in ms. */
      deadline_ms: { type: ParameterType.INT, default: undefined },
      /** Time from the answer until "Press space to continue." and Space, in ms. */
      confirmation_min_ms: { type: ParameterType.INT, default: undefined },
    },
    data: {
      /** 'left', 'right', or null on a timeout. */
      response: { type: ParameterType.STRING },
      /** `event.code` of the answer key ('KeyF' / 'KeyJ'), or null on a timeout. */
      response_key: { type: ParameterType.STRING },
      /** Answer keydown `event.timeStamp` − onset, rounded to ms; null on a timeout. */
      rt: { type: ParameterType.INT },
      is_timed_out: { type: ParameterType.BOOL },
      /** performance.now() at onset (second rAF after the reveal), ms. */
      trial_onset_time_ms: { type: ParameterType.FLOAT },
      /** Space keydown − the moment Space became accepted, ms. */
      continue_rt_ms: { type: ParameterType.INT },
      copy_attempt_count: { type: ParameterType.INT },
      blocked_shortcut_count: { type: ParameterType.INT },
      invalid_key_count: { type: ParameterType.INT },
      window_width_px: { type: ParameterType.INT },
      window_height_px: { type: ParameterType.INT },
      device_pixel_ratio: { type: ParameterType.FLOAT },
      stage_scale: { type: ParameterType.FLOAT },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    const display = CONFIG.display;

    // ---- 1. DOM, all content regions hidden ----
    const frameEl = el('div', 'frame no-select');
    const stage = el('div', 'q-stage chosen-outline');

    const questionEl = el('div', 'q-question is-hidden');
    questionEl.innerHTML = trial.question_html;
    questionEl.style.fontSize = `calc(${display.queryFontPx} * var(--u))`;

    const answersEl = el('div', 'q-answers is-hidden');
    const leftEl = answerSlot('left', trial.left_label);
    const rightEl = answerSlot('right', trial.right_label);
    answersEl.append(leftEl, rightEl);

    const messageEl = el('div', 'q-message');
    const line1 = el('div', 'q-message-line is-hidden');
    const line2 = el('div', 'q-message-line is-prompt is-hidden');
    line2.innerHTML = continuePrompt(CONFIG);
    messageEl.append(line1, line2);

    const statementsEl = el('div', 'q-statements is-hidden');
    const columnWidth = display.statementsColumnWidthPx;
    statementsEl.style.width = `calc(${columnWidth} * var(--u))`;
    statementsEl.style.left = `calc(50% - ${columnWidth / 2} * var(--u))`;
    statementsEl.style.fontSize = `calc(${display.statementFontPx} * var(--u))`;
    statementsEl.style.lineHeight = `calc(${display.statementPitchPx} * var(--u))`;
    for (const text of trial.statements) {
      const line = el('div', 'q-statement', text);
      line.style.height = `calc(${display.statementPitchPx} * var(--u))`;
      statementsEl.append(line);
    }

    stage.append(questionEl, answersEl, messageEl, statementsEl);
    frameEl.append(stage);
    displayElement.replaceChildren(frameEl);

    // ---- State ----
    const result = {
      response: null,
      response_key: null,
      rt: null,
      is_timed_out: false,
      trial_onset_time_ms: null,
      continue_rt_ms: null,
      copy_attempt_count: 0,
      blocked_shortcut_count: 0,
      invalid_key_count: 0,
      window_width_px: null,
      window_height_px: null,
      device_pixel_ratio: null,
      stage_scale: null,
    };
    let state = 'building';   // building → answering → locked → continuing → done
    let onset = null;
    let continueFrom = null;  // moment Space became accepted

    const alive = () => state !== 'done' && frameEl.isConnected;

    // ---- Listeners ----
    const onCopyLike = (e) => {
      if (!alive()) { removeListeners(); return; }
      e.preventDefault();
      if (e.type === 'copy' || e.type === 'cut' || e.type === 'contextmenu') result.copy_attempt_count += 1;
    };
    const copyEvents = ['copy', 'cut', 'contextmenu', 'selectstart', 'dragstart'];

    const onKeyDown = (e) => {
      if (!alive()) { removeListeners(); return; }
      if (e.code === 'Space' || e.key === ' ') e.preventDefault();
      if (isBlockedShortcut(e)) {
        e.preventDefault();
        if (!e.repeat) result.blocked_shortcut_count += 1;
        return;
      }
      if (e.repeat || MODIFIER_KEYS.has(e.key)) return;

      if (state === 'answering') {
        if (e.ctrlKey || e.metaKey || e.altKey) {
          result.invalid_key_count += 1;
          return;
        }
        const side = RESPONSE_CODES[e.code];
        if (side) {
          respond(side, e);
          return;
        }
        result.invalid_key_count += 1;
        return;
      }
      if (state === 'continuing' && e.code === 'Space') {
        result.continue_rt_ms = Math.round(eventTime(e) - continueFrom);
        finish();
      }
    };

    const removeListeners = () => {
      document.removeEventListener('keydown', onKeyDown, true);
      for (const type of copyEvents) document.removeEventListener(type, onCopyLike, true);
    };
    document.addEventListener('keydown', onKeyDown, true);
    for (const type of copyEvents) document.addEventListener(type, onCopyLike, true);

    // ---- 4-6. Answer, timeout, continue ----
    const enableContinue = () => {
      if (!alive()) { removeListeners(); return; }
      line2.classList.remove('is-hidden');
      continueFrom = performance.now();
      state = 'continuing';
    };

    const respond = (side, e) => {
      state = 'locked';
      result.response = side;
      result.response_key = e.code;
      result.rt = Math.round(eventTime(e) - onset);
      (side === 'left' ? leftEl : rightEl).classList.add('is-chosen');
      line1.innerHTML = confirmation(CONFIG, side === 'left' ? trial.left_label : trial.right_label);
      line1.classList.remove('is-hidden');
      this.jsPsych.pluginAPI.setTimeout(enableContinue, trial.confirmation_min_ms);
    };

    const timeOut = () => {
      if (!alive() || state !== 'answering') return;
      state = 'locked';
      result.is_timed_out = true;
      line1.innerHTML = timeoutMessage(CONFIG);
      line1.classList.remove('is-hidden');
      enableContinue();
    };

    const finish = () => {
      state = 'done';
      removeListeners();
      this.jsPsych.finishTrial({ ...result });
    };

    // ---- 2-3. Reveal, onset, enable ----
    // Lay the hidden content out first, then reveal every region in one
    // step. The reveal is made outside a frame callback, so the first
    // requestAnimationFrame runs before the frame that paints it and the
    // second runs after that frame: onset is stamped there.
    void frameEl.getBoundingClientRect();
    questionEl.classList.remove('is-hidden');
    answersEl.classList.remove('is-hidden');
    statementsEl.classList.remove('is-hidden');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!alive()) { removeListeners(); return; }
        onset = performance.now();
        result.trial_onset_time_ms = Math.round(onset * 10) / 10;
        result.window_width_px = window.innerWidth;
        result.window_height_px = window.innerHeight;
        result.device_pixel_ratio = window.devicePixelRatio;
        result.stage_scale = measureStageScale(frameEl);
        state = 'answering';
        this.jsPsych.pluginAPI.setTimeout(timeOut, trial.deadline_ms);
      });
    });
  }
}

export { QuestionTrialPlugin };
