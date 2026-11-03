/**
 * Start-up and timeline.
 *
 * Start-up:
 *   1. Load and check the item tables (js/item-tables.js) and the configuration
 *      (validateConfig).
 *   2. Choose the assignment row (js/assignments.js): assignment_id and condition.
 *   3. buildSession: every question of the session. A failure in steps 1-3 shows the
 *      build-error screen.
 *   4. Seed the global Math.random from the assignment_id.
 *   5. Wait for the fonts (at most fontLoadTimeoutMs).
 *   6. Build the timeline and run it.
 *
 * Timeline (the same in both conditions; only the questions differ): browser check, consent,
 * full screen, instructions, main intro, the main questions (a break every CONFIG.breakEvery;
 * the progress bar covers the main questions), questionnaire intro, questionnaire, save,
 * debrief, and an end screen that names the saved file.
 *
 * Every row carries `assignment_id` and `condition` (js/save.js globalTrialProperties, added
 * with jsPsych.data.addProperties).
 *
 * Data (js/save.js): the document is created at consent. Rows and fields recorded before consent
 * (the browser-check row, the summary of the session's questions) are held until then, and every
 * later row is added as it finishes. Declining saves nothing. The save screen downloads the
 * document; the end screen gives its file name and a link that downloads it again.
 *
 * Also here: on_trial_finish tidies each row (the page events of the trial, no screen HTML,
 * survey answers as JSON, browser fields to the document root); a leave-page prompt until the
 * save; a click puts the keyboard focus back on the experiment; the instruction pages' minimum
 * view.
 *
 * @module experiment
 */

import { CONFIG, validateConfig } from './config.js';
import * as copy from './copy.js';
import { loadStimuli } from './item-tables.js';
import { buildSession } from './trial-logic.js';
import { chooseAssignmentRow } from './assignments.js';
import { hashString, installSeededRandom } from './seeded-rng.js';
import {
  initDataSaving, saveSessionMetadata, saveTrialData, saveAllData,
  finalizeTrialRow, planMetadata, globalTrialProperties,
} from './save.js';
import { QuestionTrialPlugin, isBlockedShortcut } from './question-trial-plugin.js';
import {
  textScreenHtml, showPhaseProgress, updatePhaseProgress, removePhaseProgress,
  buildQuestionNode, buildContinueNode, buildBreakNode,
} from './trials.js';
import { buildInstructionPages } from './instructions.js';
import { buildQuestionnaireTrials } from './questionnaire.js';

// --- Screens drawn outside jsPsych ----------------------------------------------

function removeLoadingScreen() {
  const loading = document.getElementById('loading-screen');
  if (loading) loading.remove();
}

// Set once the session needs no leave-page prompt: at its end, or when it cannot be set up.
let experimentFinished = false;

/**
 * The build-error screen: shown when the session cannot be set up (item tables, configuration,
 * assignment row or the session's questions). Nothing is saved. The error's message follows the
 * participants' words; the console has the whole error.
 * @param {Error} error
 */
function showBuildError(error) {
  console.error('[Experiment] Setup failed; showing the build-error screen.', error);
  experimentFinished = true;
  removeLoadingScreen();
  const target = document.getElementById('jspsych-target');
  target.innerHTML = textScreenHtml({ paragraphs: [copy.buildError(CONFIG)] });
  const reason = document.createElement('p');
  reason.textContent = error && error.message ? error.message : String(error);
  target.querySelector('.text-screen').append(reason);
}

/** `text` with the HTML special characters escaped. */
function escapeHtml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * The last screen, after the debrief: the session is over and its record was downloaded under
 * its file name, with a link that downloads it again, or why the record could not be saved.
 * @param {?{fileName?: string, url?: string, error?: Error}} saved
 * @returns {string[]} HTML paragraphs.
 */
function endScreenParagraphs(saved) {
  if (saved && saved.fileName) {
    const name = escapeHtml(saved.fileName);
    return [
      `The session is over, and your browser was asked to save its record as ${name}.`,
      `If no file was saved, <a href="${saved.url}" download="${name}">download it here</a>.`,
    ];
  }
  const reason = saved && saved.error ? saved.error.message : 'the record was not created';
  return [`The session is over, but its record could not be saved: ${escapeHtml(reason)}`];
}

// --- Fonts --------------------------------------------------------------------------

/**
 * Keep both Inter weights in use on the page for the whole session. WebKit unloads a face that
 * no rendered text uses, and with `font-display: block` a face that reloads later would hide the
 * first bold word of a question for up to the block period. One invisible, off-screen line in
 * each weight prevents that.
 */
function mountFontKeepalive() {
  const keep = document.createElement('div');
  keep.className = 'font-keepalive';
  keep.setAttribute('aria-hidden', 'true');
  keep.innerHTML = '<span class="font-keepalive-regular">Aa</span><span class="font-keepalive-semibold">Aa</span>';
  document.body.append(keep);
}

/** Wait for Inter 400 and 600, at most fontLoadTimeoutMs. */
async function awaitFonts() {
  let timer = null;
  const loads = Promise.all([document.fonts.load('400 22px Inter'), document.fonts.load('600 24px Inter')])
    .catch((err) => { console.warn('[Fonts] Load failed:', err); });
  const cap = new Promise((resolve) => { timer = setTimeout(resolve, CONFIG.fontLoadTimeoutMs); });
  await Promise.race([loads, cap]);
  clearTimeout(timer);
}

// --- Full screen ----------------------------------------------------------------------

/**
 * Catch refused full-screen requests. jsPsych's fullscreen plugin (the only screen that requests
 * full screen) calls document.documentElement.requestFullscreen() without handling a rejection,
 * which surfaces as an uncaught error when the browser refuses. The request itself is unchanged;
 * a refusal calls `onDenied(error)`.
 * @param {function(Error): void} onDenied
 */
function guardFullscreenRequests(onDenied) {
  const el = document.documentElement;
  for (const name of ['requestFullscreen', 'webkitRequestFullscreen']) {
    const original = el[name];
    if (typeof original !== 'function') continue;
    el[name] = function guardedFullscreenRequest(...args) {
      let result;
      try {
        result = original.apply(this, args);
      } catch (err) {
        onDenied(err);
        return Promise.resolve();
      }
      return (result && typeof result.catch === 'function') ? result.catch((err) => { onDenied(err); }) : result;
    };
  }
}

// --- Copy and find blocking outside the question screens ------------------------------

/**
 * Block copy, selection, the context menu and the find, print and save shortcuts on every screen
 * whose content is `.no-select` (all but consent and the questionnaire). The question screens
 * also block these themselves and count them (js/question-trial-plugin.js).
 * @param {object} jsPsych
 */
function installScreenCopyBlocking(jsPsych) {
  const active = () => {
    const display = jsPsych.getDisplayElement();
    return Boolean(display && display.querySelector('.no-select'));
  };
  for (const type of ['copy', 'cut', 'contextmenu', 'selectstart', 'dragstart']) {
    document.addEventListener(type, (e) => {
      if (active()) e.preventDefault();
    }, true);
  }
  // The same shortcuts as the question screens.
  document.addEventListener('keydown', (e) => {
    if (active() && isBlockedShortcut(e)) e.preventDefault();
  }, true);
}

// --- Main -----------------------------------------------------------------------------

async function startExperiment() {
  // Item tables, configuration, assignment row, the session's questions.
  let session;
  let tables;
  let assignment;
  try {
    ({ tables } = await loadStimuli());
    validateConfig(CONFIG, tables);
    assignment = await chooseAssignmentRow();
    session = await buildSession(assignment, CONFIG, tables);
  } catch (error) {
    showBuildError(error);
    return;
  }
  const assignmentId = assignment.assignment_id;
  const condition = assignment.condition;
  console.log(`[Experiment] assignment_id ${assignmentId} (${condition}); schedule ${session.schedule_sha256}.`);

  // The global Math.random, seeded from assignment_id, for incidental use only; the questions
  // never draw from it.
  const seed = hashString(String(assignmentId));
  installSeededRandom(seed);

  mountFontKeepalive();
  await awaitFonts();

  // Session fields known now; held by js/save.js until consent.
  saveSessionMetadata({ prng_seed: seed, ...planMetadata(session) });

  // --- jsPsych and the data path ---
  // Blur/focus/fullscreen events, keyed by the trial index current when they fired. An event in
  // the blank after a trial is keyed to that trial but arrives after its row was saved, so every
  // row takes all the events not yet saved up to its own index.
  const pendingInteractionEvents = {};
  const drainInteractionEvents = (trialIndex) => {
    const events = [];
    for (const key of Object.keys(pendingInteractionEvents)) {
      if (Number(key) <= trialIndex) {
        events.push(...pendingInteractionEvents[key]);
        delete pendingInteractionEvents[key];
      }
    }
    return events.sort((a, b) => a.time_ms - b.time_ms);
  };

  const jsPsych = initJsPsych({
    display_element: 'jspsych-target',
    on_interaction_data_update: (event) => {
      (pendingInteractionEvents[event.trial] ??= []).push({ event: event.event, time_ms: event.time });
    },
    on_trial_start: (trial) => {
      // The progress band shows on the questions only; the breaks draw their own bar.
      if (trial.type === QuestionTrialPlugin) showPhaseProgress(true);
      else removePhaseProgress();
    },
    on_trial_finish: (data) => {
      // Tidy the row (this trial's blur/focus/fullscreen events, no screen HTML, survey
      // response_json, browser fields to the document), then save it.
      const events = drainInteractionEvents(data.trial_index);
      const { browser_metadata: browserMetadata } = finalizeTrialRow(data, events);
      if (browserMetadata) saveSessionMetadata({ browser_metadata: browserMetadata });
      saveTrialData(data);
    },
    on_finish: () => { experimentFinished = true; },
  });

  window.addEventListener('beforeunload', (e) => {
    if (experimentFinished) return;
    e.preventDefault();
    e.returnValue = '';
  });
  // Keep keyboard focus inside the experiment.
  document.addEventListener('click', () => {
    const target = document.getElementById('jspsych-target');
    if (target && !target.contains(document.activeElement)) target.focus();
  });
  installScreenCopyBlocking(jsPsych);
  // A refused full-screen request (e.g. no permission) is logged on the current row as a
  // 'fullscreen_denied' event instead of an uncaught error.
  guardFullscreenRequests(() => {
    const index = jsPsych.getProgress().current_trial_global;
    (pendingInteractionEvents[index] ??= []).push({ event: 'fullscreen_denied', time_ms: jsPsych.getTotalTime() });
  });

  // --- Instructions (minimum view, Back and Next in the bottom bar) ---

  /**
   * Instruction minimum view: Next is dimmed and disabled for instructionMinViewMs on the first
   * view of each page. A page counts as seen only once its full minimum view has run, so leaving
   * it early (Back) and returning restarts the wait.
   */
  function instructionMinViewCallbacks() {
    const visited = new Set();
    let timer = null;
    const updateNav = () => {
      const next = document.getElementById('jspsych-instructions-next');
      if (!next) return;
      const waiting = timer !== null;
      next.disabled = waiting;
      next.classList.toggle('is-dimmed', waiting);
    };
    const handlePage = (index) => {
      if (timer) { clearTimeout(timer); timer = null; }
      if (!visited.has(index)) {
        timer = setTimeout(() => {
          timer = null;
          visited.add(index);
          updateNav();
        }, CONFIG.instructionMinViewMs);
      }
      updateNav();
    };
    return {
      on_load: () => handlePage(0),
      on_page_change: handlePage,
    };
  }

  function makeInstructionsNode() {
    const ins = buildInstructionPages(CONFIG, tables);
    const minView = instructionMinViewCallbacks();
    // jsPsych's instructions plugin draws its own buttons under the page; move them into the
    // page's frame as the fixed bottom bar, with the copy.js labels and the shared classes.
    const decorate = (index) => {
      const display = jsPsych.getDisplayElement();
      const frame = display.querySelector('.frame');
      const nav = display.querySelector('.jspsych-instructions-nav');
      if (!frame || !nav) return;
      nav.removeAttribute('style');
      nav.classList.add('nav-bar');
      frame.append(nav);
      const back = nav.querySelector('#jspsych-instructions-back');
      const next = nav.querySelector('#jspsych-instructions-next');
      for (const [button, label, cls] of [[back, ins.backButton, 'btn'], [next, ins.nextButton, 'btn btn-primary']]) {
        if (!button) continue;
        button.removeAttribute('style');
        button.className = cls;
        button.type = 'button';
        button.innerHTML = label;
      }
      if (back && index === 0) back.classList.add('is-hidden');
    };
    return {
      type: jsPsychInstructions,
      pages: ins.pages,
      show_clickable_nav: true,
      allow_backward: true,
      allow_keys: false,
      // The step ids in display order, so the row's view_history page indices can be read
      // without the code.
      data: {
        phase: 'instructions',
        instruction_page_ids_json: JSON.stringify(ins.ids),
      },
      on_load: () => {
        decorate(0);
        minView.on_load();
      },
      on_page_change: (index) => {
        if (index >= ins.pages.length) return;   // the last Next ended the trial
        decorate(index);
        minView.on_page_change(index);
      },
    };
  }

  // --- Main questions and breaks ---

  const barTotal = session.main.length;
  const barUpdate = (position) => () => updatePhaseProgress(position, barTotal);
  updatePhaseProgress(0, barTotal);   // an empty bar at the first question

  const mainNodes = [
    buildContinueNode('main_intro', copy.mainIntro(CONFIG), { minViewMs: CONFIG.mainIntroMinViewMs }),
  ];
  session.main.forEach((t, i) => {
    const finished = i + 1;
    mainNodes.push(buildQuestionNode(t, { onFinish: barUpdate(finished) }));
    if (finished % CONFIG.breakEvery === 0 && finished < session.main.length) {
      // The break's own bar (the top band is hidden on breaks), at the same position as the
      // band.
      mainNodes.push({
        ...buildBreakNode(finished / barTotal),
        on_start: barUpdate(finished),
      });
    }
  });

  // --- Timeline ---

  const timeline = [];

  // Browser check (visible only when it fails).
  const browserCopy = copy.browserCheck(CONFIG);
  timeline.push({
    type: jsPsychBrowserCheck,
    minimum_width: CONFIG.browser.minWidth,
    minimum_height: CONFIG.browser.minHeight,
    // While the window is too small the participant may enlarge it; the button gives up and
    // shows the exclusion message.
    window_resize_message: textScreenHtml({ paragraphs: [browserCopy.resize] }, { flow: true }),
    resize_fail_button_text: browserCopy.resizeButton,
    inclusion_function: (d) => !d.mobile,
    exclusion_message: (d) => textScreenHtml({
      paragraphs: [d.mobile ? browserCopy.mobile : browserCopy.windowTooSmall],
    }, { flow: true }),
    data: { phase: 'browser_check' },
  });

  // Consent. The document is created on "I agree"; declining saves nothing.
  const consentCopy = copy.consent(CONFIG);
  let consentGiven = false;
  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `<div class="consent">${consentCopy.html}<div class="ts-actions">`
      + `<button type="button" class="btn btn-primary" id="consent-agree">${consentCopy.agreeButton}</button>`
      + `<button type="button" class="btn" id="consent-decline">${consentCopy.declineButton}</button>`
      + '</div></div>',
    choices: 'NO_KEYS',
    data: { phase: 'consent' },
    on_load: () => {
      document.getElementById('consent-agree').addEventListener('click', () => {
        jsPsych.finishTrial({ consent_given: true });
      });
      document.getElementById('consent-decline').addEventListener('click', () => {
        jsPsych.finishTrial({ consent_given: false });
      });
    },
    on_finish: (data) => {
      consentGiven = data.consent_given === true;
      if (consentGiven) initDataSaving({ assignmentId, condition });
    },
  });
  timeline.push({
    timeline: [{
      type: jsPsychHtmlKeyboardResponse,
      stimulus: textScreenHtml({ paragraphs: [copy.consentDeclined(CONFIG)] }),
      choices: 'NO_KEYS',
      data: { phase: 'consent_declined' },
      on_load: () => { experimentFinished = true; },
    }],
    conditional_function: () => !consentGiven,
  });

  // Full screen.
  const fullscreenCopy = copy.fullscreen(CONFIG);
  timeline.push({
    type: jsPsychFullscreen,
    fullscreen_mode: true,
    message: textScreenHtml({ title: fullscreenCopy.title, paragraphs: [fullscreenCopy.text] }),
    button_label: fullscreenCopy.button,
    data: { phase: 'fullscreen' },
    on_load: () => {
      // The plugin puts its button after the message; move it under the text.
      const display = jsPsych.getDisplayElement();
      const button = display.querySelector('#jspsych-fullscreen-btn');
      const column = display.querySelector('.text-screen');
      if (!button || !column) return;
      button.className = 'btn btn-primary';
      button.type = 'button';
      const actions = document.createElement('div');
      actions.className = 'ts-actions';
      actions.append(button);
      column.append(actions);
    },
  });

  // Instructions, the main questions and the questionnaire.
  timeline.push(
    makeInstructionsNode(),
    ...mainNodes,
    buildContinueNode('questionnaire_intro', copy.questionnaireIntro(CONFIG)),
    ...buildQuestionnaireTrials(),
  );

  // Save (the download), the debrief, then the end screen. A failed save does not stop the
  // session; the end screen shows the error.
  let saved = null;
  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: textScreenHtml({ paragraphs: [copy.saveData(CONFIG)] }, { centered: true }),
    choices: 'NO_KEYS',
    data: { phase: 'save_data' },
    on_load: async () => {
      try {
        saved = await saveAllData(JSON.parse(jsPsych.data.get().json()));
      } catch (error) {
        console.error('[save] The record could not be saved.', error);
        saved = { error };
      } finally {
        experimentFinished = true;   // no leave-page prompt from here on
        jsPsych.finishTrial();
      }
    },
  });
  timeline.push(buildContinueNode('debrief', copy.debrief(CONFIG), { centered: false }));
  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: () => textScreenHtml({ paragraphs: endScreenParagraphs(saved) }, { centered: true }),
    choices: 'NO_KEYS',
  });

  jsPsych.data.addProperties(globalTrialProperties({ assignmentId, condition }));

  removeLoadingScreen();
  console.log(`[Experiment] Timeline built: ${timeline.length} top-level nodes.`);
  jsPsych.run(timeline);
}

startExperiment().catch((error) => {
  showBuildError(error);
});
