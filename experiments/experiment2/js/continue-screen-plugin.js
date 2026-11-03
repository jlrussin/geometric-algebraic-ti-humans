/**
 * ContinueScreenPlugin (`continue-screen`): a text screen that Space ends. Used for the main and
 * questionnaire intros, the breaks and the debrief.
 *
 * Space ends the screen when it is a fresh press (not an auto-repeat) made after `lockout_ms`
 * (continueLockoutFrames) and `min_view_ms` (e.g. mainIntroMinViewMs) have both passed. A Space
 * pressed or held during the wait therefore has to be released and pressed again; other keys
 * never block it. While a minimum view longer than the lockout runs, the screen's "Press space
 * ..." line (`.ts-prompt`) is dimmed, like Next on the instruction pages.
 *
 * The acceptance moment (for `continue_rt_ms`) is the end of the wait, or, if non-modifier keys
 * were still held then, their release; lock and modifier keys are not tracked (macOS sends
 * CapsLock's keyup only when it is switched off). If a keyup was missed, a fresh Space still ends
 * the screen and the acceptance moment is the end of the wait.
 *
 * Records `continue_rt_ms` (Space keydown − the moment Space became accepted),
 * `screen_duration_ms` (Space keydown − first paint of the screen) and `is_fullscreen` (at the
 * Space press).
 *
 * @module continue-screen-plugin
 */

import { eventTime } from './question-trial-plugin.js';

const { ParameterType } = window.jsPsychModule;

// Keys currently held down, tracked for the whole page from module load, so
// a key still held from the previous screen blocks acceptance here. Lock and
// modifier keys are left out. macOS sends no keyup for a key released while
// Cmd is down, so releasing Cmd clears the set; so do leaving the window and
// hiding the page.
const UNTRACKED_CODES = new Set([
  '', 'CapsLock', 'NumLock', 'ScrollLock', 'Fn', 'FnLock',
  'ShiftLeft', 'ShiftRight', 'ControlLeft', 'ControlRight', 'AltLeft', 'AltRight',
  'MetaLeft', 'MetaRight', 'OSLeft', 'OSRight',
]);
const heldCodes = new Set();
document.addEventListener('keydown', (e) => {
  if (!UNTRACKED_CODES.has(e.code)) heldCodes.add(e.code);
}, true);
document.addEventListener('keyup', (e) => {
  if (e.key === 'Meta') heldCodes.clear();
  else heldCodes.delete(e.code);
}, true);
window.addEventListener('blur', () => heldCodes.clear());
document.addEventListener('visibilitychange', () => { if (document.hidden) heldCodes.clear(); });

function isFullscreen() {
  return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
}

class ContinueScreenPlugin {
  static info = {
    name: 'continue-screen',
    version: '1.0.0',
    parameters: {
      /** The screen's HTML (a text screen built from js/copy.js). */
      stimulus: { type: ParameterType.HTML_STRING, default: undefined },
      /** Keys are ignored for this long after the screen appears, ms. */
      lockout_ms: { type: ParameterType.INT, default: undefined },
      /** Optional minimum view time before Space is accepted, ms. */
      min_view_ms: { type: ParameterType.INT, default: 0 },
    },
    data: {
      /** Space keydown − the moment Space became accepted, ms. */
      continue_rt_ms: { type: ParameterType.INT },
      /** Space keydown − the first paint of the screen, ms. */
      screen_duration_ms: { type: ParameterType.INT },
      /** Whether the page was in full screen at the Space press. */
      is_fullscreen: { type: ParameterType.BOOL },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    displayElement.innerHTML = trial.stimulus;
    const root = displayElement.firstElementChild;
    const prompt = displayElement.querySelector('.ts-prompt');
    const waitMs = Math.max(trial.lockout_ms, trial.min_view_ms || 0);
    const dimPrompt = prompt && trial.min_view_ms > trial.lockout_ms;
    if (dimPrompt) prompt.classList.add('is-dimmed');

    let shownAt = null;
    let waitOver = false;
    let waitOverAt = null;
    let acceptedAt = null;
    let done = false;
    const alive = () => !done && (!root || root.isConnected);

    const accept = () => {
      if (acceptedAt !== null || !waitOver || heldCodes.size > 0) return;
      acceptedAt = performance.now();
    };

    const onKeyDown = (e) => {
      if (!alive()) { removeListeners(); return; }
      if (e.code === 'Space' || e.key === ' ') e.preventDefault();
      if (e.code !== 'Space' || e.repeat || !waitOver) return;
      // A fresh Space press after the wait: Space was released, whatever the
      // tracker says about other keys (a missed keyup must not deadlock).
      if (acceptedAt === null) acceptedAt = waitOverAt;
      const t = eventTime(e);
      done = true;
      removeListeners();
      this.jsPsych.finishTrial({
        continue_rt_ms: Math.round(t - acceptedAt),
        screen_duration_ms: Math.round(t - shownAt),
        is_fullscreen: isFullscreen(),
      });
    };
    const onKeyUp = () => {
      if (!alive()) { removeListeners(); return; }
      // The page-level tracker (registered first, in the capturing phase) has already removed
      // this key; accept once nothing is held.
      accept();
    };
    const removeListeners = () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('keyup', onKeyUp, true);
    };
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('keyup', onKeyUp, true);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!alive()) { removeListeners(); return; }
        shownAt = performance.now();
        this.jsPsych.pluginAPI.setTimeout(() => {
          if (!alive()) { removeListeners(); return; }
          if (dimPrompt) prompt.classList.remove('is-dimmed');
          waitOver = true;
          waitOverAt = performance.now();
          accept();
        }, waitMs);
      });
    });
  }
}

export { ContinueScreenPlugin };
