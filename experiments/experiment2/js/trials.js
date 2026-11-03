/**
 * jsPsych timeline nodes and the screen helpers.
 *
 * The questions are computed in js/trial-logic.js (pure); this module wraps its {params, record}
 * trials in nodes and holds:
 *   - question nodes (QuestionTrialPlugin), scored in on_finish;
 *   - continue screens and breaks (ContinueScreenPlugin);
 *   - the text-screen markup;
 *   - the thin progress bar, mounted on document.body outside the jsPsych display element so
 *     that it stays through the blank between questions.
 *
 * All participant-facing words come from js/copy.js, except the closing screen of a local
 * session and the start-up fallback (js/experiment.js, index.html).
 *
 * @module trials
 */

import { CONFIG, framesToMs } from './config.js';
import { scoreResponse } from './trial-logic.js';
import * as copy from './copy.js';
import { QuestionTrialPlugin } from './question-trial-plugin.js';
import { ContinueScreenPlugin } from './continue-screen-plugin.js';

// --- Text screens -----------------------------------------------------------------

function paragraphsHtml(paragraphs) {
  return (paragraphs || []).map((p) => `<p>${p}</p>`).join('');
}

/**
 * A text screen in the 640-px column from a copy.js object
 * {title?, heading?, paragraphs, reminder?, prompt?}: title, section heading, progress bar,
 * paragraphs, reminder, then the "Press space ..." line. Used by every text screen: the build
 * error (drawn outside jsPsych) and the screens of consent declined, saving, the browser check,
 * full screen, the intros, the breaks and the debrief.
 * @param {{title?: string, heading?: string, paragraphs: string[], reminder?: string,
 *   prompt?: string}} content - HTML from js/copy.js.
 * @param {object} [opts]
 * @param {?number} [opts.progress=null] - A progress bar above the paragraphs, filled to this
 *   fraction (the breaks); the column then gets `.has-progress` (one-line items, evenly
 *   spaced).
 * @param {boolean} [opts.centered=false] - Centered text in the middle of the frame (continue
 *   screens, saving).
 * @param {boolean} [opts.flow=false] - No 1024 × 700 frame: the column flows in the page and
 *   narrows to the window, for the browser-check screens, which are drawn in windows smaller
 *   than the frame.
 * @returns {string}
 */
export function textScreenHtml(content, { flow = false, progress = null, centered = false } = {}) {
  const title = content.title ? `<h1 class="ts-title">${content.title}</h1>` : '';
  const heading = content.heading ? `<h2 class="ts-heading">${content.heading}</h2>` : '';
  const bar = progress === null ? ''
    : `<div class="ts-progress" aria-hidden="true"><div class="ts-progress-fill" style="width: ${(progress * 100).toFixed(3)}%"></div></div>`;
  const reminder = content.reminder ? `<p class="ts-reminder">${content.reminder}</p>` : '';
  const prompt = content.prompt ? `<p class="ts-prompt">${content.prompt}</p>` : '';
  const body = `${title}${heading}${bar}${paragraphsHtml(content.paragraphs)}${reminder}${prompt}`;
  if (flow) return `<div class="text-screen is-flow no-select">${body}</div>`;
  const classes = ['text-screen', centered ? 'is-centered' : '', progress === null ? '' : 'has-progress']
    .filter(Boolean).join(' ');
  return `<div class="frame no-select"><div class="${classes}">${body}</div></div>`;
}

// --- Progress bar -------------------------------------------------------------------

let progressBand = null;
let progressFill = null;

/** Mount the band once: `.progress-band > .progress-track > .progress-fill`. */
function ensureProgressBand() {
  if (progressBand) return;
  progressBand = document.createElement('div');
  progressBand.className = 'progress-band is-hidden';
  progressBand.setAttribute('aria-hidden', 'true');
  const track = document.createElement('div');
  track.className = 'progress-track';
  progressFill = document.createElement('div');
  progressFill.className = 'progress-fill';
  track.append(progressFill);
  progressBand.append(track);
  document.body.append(progressBand);
}

/**
 * Show or hide the progress band. It is `position: fixed` on document.body, outside the display
 * element, so it stays through the blank between questions. Shown on the questions; hidden on
 * every other screen (the breaks draw their own bar).
 * @param {boolean} show
 */
export function showPhaseProgress(show) {
  ensureProgressBand();
  progressBand.classList.toggle('is-hidden', !show);
}

/**
 * Fill the bar to completed / total (questions finished, never accuracy; no count is shown).
 * The fill's short width transition plays in the blank after a question.
 * @param {number} completed
 * @param {number} total
 */
export function updatePhaseProgress(completed, total) {
  ensureProgressBand();
  if (!(total > 0)) return;
  const done = Math.max(0, Math.min(total, completed));
  progressFill.style.width = `${((done / total) * 100).toFixed(3)}%`;
}

/** Hide the band. */
export function removePhaseProgress() {
  if (progressBand) progressBand.classList.add('is-hidden');
}

// --- Question nodes -----------------------------------------------------------------

/**
 * Wrap one trial-logic trial {params, record} as a question node.
 *
 * - The plugin gets `params` (display strings and durations only); the `record` goes in the
 *   node's `data`, which jsPsych merges into the saved row.
 * - on_finish adds `chosen_item`, `is_correct` and `is_knowledge_consistent` (trial-logic's
 *   scoreResponse), then calls `onFinish(data)` (the progress bar update, which lands in the
 *   blank that follows).
 * - The blank after the question is `post_trial_gap` = itiFrames.
 *
 * @param {{params: object, record: object}} t
 * @param {object} [opts]
 * @param {function(object): void} [opts.onFinish]
 * @returns {object} A timeline node.
 */
export function buildQuestionNode(t, { onFinish = null } = {}) {
  return {
    type: QuestionTrialPlugin,
    ...t.params,
    data: { ...t.record },
    post_trial_gap: framesToMs(CONFIG.timing.itiFrames),
    on_finish: (data) => {
      Object.assign(data, scoreResponse(data));
      if (onFinish) onFinish(data);
    },
  };
}

// --- Continue screens and breaks ----------------------------------------------------

/**
 * A continue screen (Space to go on) from a copy.js object {title?, heading?, paragraphs,
 * reminder?, prompt}.
 * @param {string} phase - The row's `phase`.
 * @param {object} content - The copy.js object.
 * @param {object} [opts]
 * @param {number} [opts.minViewMs=0]
 * @param {?number} [opts.progress=null] - A progress bar above the text, at this fraction.
 * @param {boolean} [opts.centered=true] - Centered layout (false for the debrief, which is
 *   left-aligned).
 * @returns {object} A timeline node.
 */
export function buildContinueNode(phase, content, {
  minViewMs = 0, progress = null, centered = true,
} = {}) {
  return {
    type: ContinueScreenPlugin,
    stimulus: () => textScreenHtml(content, { progress, centered }),
    lockout_ms: framesToMs(CONFIG.timing.continueLockoutFrames),
    min_view_ms: minViewMs,
    data: { phase },
  };
}

/**
 * A break: a progress bar (no counts), "Take a short break if you need one.", the bonus reminder
 * and "Press space to continue.", one line each. The row records `is_fullscreen`
 * (ContinueScreenPlugin) and the page events of the screen.
 * @param {number} progress - Fraction of the main questions finished, for the bar.
 * @returns {object} A timeline node.
 */
export function buildBreakNode(progress) {
  return buildContinueNode('break', copy.breakScreen(CONFIG), { progress });
}
