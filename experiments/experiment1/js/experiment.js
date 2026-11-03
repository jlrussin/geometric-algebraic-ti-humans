/**
 * Experiment 1: the session's startup and its timeline.
 *
 * The session runs: browser check, consent, fullscreen, three instruction blocks (query,
 * single step, multistep), each with a comprehension check and practice, the experiment
 * overview with a final comprehension check, the learning phase, the three tests, a
 * questionnaire, the save and a closing screen. A session that fails a comprehension check
 * twice ends there, after the save.
 *
 * The assignment row sets the order of the tests and seeds the random number generator, which
 * then assigns the stimuli and builds every trial before the first screen.
 *
 * @module experiment
 */

import { CONFIG } from './config.js';
import { initStimuliState, getStimuliSnapshot } from './stimuli.js';
import { LinkedListDisplayPlugin, preloadImages } from './display.js';
import { querySideTracker, distractorsBetweenTracker, queryPairTracker } from './utils.js';
import { chooseAssignment } from './assignments.js';
import {
  buildQueryOnlyPracticeTrials,
  buildSinglehopPracticeTrials, buildMultiHopPracticeTrials,
  buildTrainingBlock,
  buildICLTestBlock, buildIWLTestBlock, buildArbitrageTestBlock,
  buildComprehensionBlock, buildPracticePreamble, buildPostPracticeScreen,
  buildFailedScreenTrial, unlessFailed, ifFailed,
  comprehensionState, practiceState, failureState,
  buildBreakNode,
  showPhaseProgress, updatePhaseProgress, removePhaseProgress,
  recordTestPoint, getPerformancePoints,
} from './trials.js';
import { generateTestPairHistogram } from './trial-logic.js';
import { initDataSaving, saveSessionMetadata, saveTrialData, saveAllData } from './save.js';
import {
  buildWarningPages,
  buildQueryInstructionPages, queryHelpIntroPageIndex,
  buildSinglehopInstructionPages,
  buildMultihopInstructionPages,
  buildExperimentOverview, buildPreTrainingSummary,
  buildTransitionPages,
} from './instructions.js';
import {
  initHelpSystem, beginTrial as helpBeginTrial, endTrial as helpEndTrial,
  setBadgeVisible as helpSetBadgeVisible,
  getSessionStats as helpGetSessionStats,
  hasOpenedHelp as helpHasOpenedHelp,
  onFirstOpen as helpOnFirstOpen,
} from './help.js';
import { buildQuestionnaireTrials } from './questionnaire.js';
import { CONSENT_HTML, THANK_YOU_HTML } from './consent.js';
import { hashString, installSeededRandom } from './seeded-rng.js';

// The task's own jsPsych plugin, under the global name its timeline nodes use.
window.jsPsychLinkedListDisplay = LinkedListDisplayPlugin;

async function startExperiment() {
  const distractorWeightSum = Object.values(CONFIG.distractorsBetweenDist)
    .reduce((a, b) => a + b, 0);
  if (Math.abs(distractorWeightSum - 1) > 1e-6) {
    throw new Error(`distractorsBetweenDist weights must sum to 1 (got ${distractorWeightSum})`);
  }

  // The assignment is chosen before the generator is seeded, since the seed depends on it.
  const assignment = await chooseAssignment();
  const assignmentId = assignment.assignment_id;
  installSeededRandom(hashString(String(assignmentId)));

  // Browser events (blur, focus, fullscreen changes), collected per trial and saved on the
  // trial's row.
  const pendingInteractionEvents = {};

  // Zero-duration helper screens that show or remove the progress bar; their rows are not saved.
  const UNSAVED_PHASES = new Set(['progress_setup', 'progress_teardown']);

  const jsPsych = initJsPsych({
    display_element: 'jspsych-target',
    on_interaction_data_update: (event) => {
      (pendingInteractionEvents[event.trial] ??= []).push({
        event: event.event,
        time_ms: event.time,
      });
    },
    on_trial_start: (trial) => {
      // The help button follows the phase of every screen: task trials carry `phase` as a
      // plugin parameter, other screens as `data.phase`.
      const phase = trial.phase ?? trial.data?.phase ?? null;
      const helpContext = trial.data?.help_context ?? null;
      if (phase) helpBeginTrial(phase, helpContext);
    },
    on_trial_finish: (data) => {
      const events = pendingInteractionEvents[data.trial_index] || [];
      data.interaction_events_json = JSON.stringify(events);
      delete pendingInteractionEvents[data.trial_index];

      delete data.internal_node_id;
      delete data.plugin_version;

      // Questionnaire answers are saved as one JSON string, without the progress header that
      // SurveyJS records as an element of its own.
      if (data.trial_type === 'survey' && data.response && typeof data.response === 'object') {
        const filtered = {};
        for (const [k, v] of Object.entries(data.response)) {
          if (!k.startsWith('progress_')) filtered[k] = v;
        }
        data.response_json = JSON.stringify(filtered);
        delete data.response;
      }

      // The browser and screen are recorded once, on the session record, not on the row.
      if (data.trial_type === 'browser-check') {
        saveSessionMetadata({
          browser_metadata: {
            browser:          data.browser,
            browser_version:  data.browser_version,
            os:               data.os,
            is_mobile:        data.mobile,
            window_width_px:  data.width ?? data.window_width,
            window_height_px: data.height ?? data.window_height,
            screen_width_px:  data.screen_width,
            screen_height_px: data.screen_height,
            device_pixel_ratio: data.device_pixel_ratio,
            vsync_rate_hz:    data.vsync_rate,
          },
        });
        delete data.browser;
        delete data.browser_version;
        delete data.os;
        delete data.mobile;
        delete data.width;
        delete data.height;
        delete data.window_width;
        delete data.window_height;
        delete data.vsync_rate;
        delete data.fullscreen;
        delete data.microphone;
        delete data.webaudio;
        delete data.webcam;
      }

      // Screen HTML is not saved; the code rebuilds it.
      delete data.stimulus;
      delete data.message;
      delete data.pages;

      Object.assign(data, helpEndTrial());

      if (!UNSAVED_PHASES.has(data.phase)) {
        saveTrialData(data);
      }
    },
  });

  // Ask before leaving the page until the data are saved.
  let experimentFinished = false;
  window.addEventListener('beforeunload', (e) => {
    if (experimentFinished) return;
    e.preventDefault();
    e.returnValue = '';
  });

  // jsPsych listens for keys on its display element; a click elsewhere on the page would move
  // the focus away from it, so every click returns the focus there.
  document.addEventListener('click', () => {
    const target = document.getElementById('jspsych-target');
    if (!target) return;
    if (!target.contains(document.activeElement)) target.focus();
  });

  initStimuliState();
  const preloadResult = await preloadImages();

  const loadingScreen = document.getElementById('loading-screen');
  if (loadingScreen) loadingScreen.remove();

  initDataSaving({ assignmentId });
  saveSessionMetadata({
    test_block_order: assignment.test_block_order,
    stimuli: getStimuliSnapshot(),
    preload: {
      duration_ms:   preloadResult.durationMs,
      images_loaded: preloadResult.loaded,
      images_failed: preloadResult.failed,
    },
  });

  initHelpSystem();

  // --- Instruction pages: minimum viewing time ---
  //
  // The navigation buttons stay disabled for CONFIG.instructionMinViewMs on the first visit to
  // each page of an instruction sequence. After a failed comprehension check
  // (comprehensionState.needsReset[blockId]) every page counts as unvisited again.
  // `extraDisable(page)` can keep Next disabled for other reasons.
  function instructionMinViewCallbacks(blockId = null, { extraDisable = null } = {}) {
    const visitedPages = new Set();
    let timer = null;
    let currentPage = 0;

    function setButtonState(btn, enabled) {
      btn.disabled = !enabled;
      btn.style.opacity = enabled ? '' : '0.4';
      btn.style.cursor = enabled ? '' : 'default';
    }

    function isExtraDisabled() {
      return typeof extraDisable === 'function' && !!extraDisable(currentPage);
    }

    function updateNav() {
      const prevBtn = document.getElementById('jspsych-instructions-back');
      const nextBtn = document.getElementById('jspsych-instructions-next');
      const timerActive = timer !== null;
      const extra = isExtraDisabled();
      if (prevBtn) setButtonState(prevBtn, currentPage > 0 && !timerActive);
      if (nextBtn) setButtonState(nextBtn, !timerActive && !extra);
    }

    function handlePage(pageIndex) {
      currentPage = pageIndex;
      if (timer) { clearTimeout(timer); timer = null; }
      if (!visitedPages.has(pageIndex)) {
        visitedPages.add(pageIndex);
        timer = setTimeout(() => { timer = null; updateNav(); }, CONFIG.instructionMinViewMs);
      }
      updateNav();
    }

    return {
      on_load: () => {
        if (blockId && comprehensionState.needsReset[blockId]) {
          visitedPages.clear();
          comprehensionState.needsReset[blockId] = false;
        }
        handlePage(0);
      },
      on_page_change: (pageIndex) => handlePage(pageIndex),
      // Re-enable the buttons if an outside condition (the help panel was opened) changed.
      recheck: () => updateNav(),
    };
  }

  // The instructions node of a block. While the page `helpBadgePageIndex` is shown, the help
  // button is visible, and Next stays disabled until the participant has opened the help panel.
  // `instruction-active` on <body> anchors instruction pages to the top of the window.
  function makeInstructionsNode(blockId, pages, { helpBadgePageIndex = null } = {}) {
    const extraDisable = (helpBadgePageIndex === null)
      ? null
      : (idx) => idx === helpBadgePageIndex && !helpHasOpenedHelp();
    const minView = instructionMinViewCallbacks(blockId, { extraDisable });
    let firstOpenRegistered = false;
    const ensureFirstOpenRecheck = () => {
      if (firstOpenRegistered) return;
      firstOpenRegistered = true;
      helpOnFirstOpen(() => minView.recheck());
    };
    const showHelpFor = (idx) => {
      if (helpBadgePageIndex !== null) {
        helpSetBadgeVisible(idx === helpBadgePageIndex);
        if (idx === helpBadgePageIndex) ensureFirstOpenRecheck();
      }
    };
    return {
      type: jsPsychInstructions,
      pages,
      show_clickable_nav: true,
      allow_backward: true,
      allow_keys: false,
      button_label_previous: 'Previous',
      button_label_next: 'Next',
      data: { phase: `instructions_${blockId}`, comprehension_block_id: blockId },
      on_load: () => {
        document.body.classList.add('instruction-active');
        minView.on_load();
        showHelpFor(0);
      },
      on_finish: () => {
        document.body.classList.remove('instruction-active');
      },
      on_page_change: (pageIndex) => {
        minView.on_page_change(pageIndex);
        showHelpFor(pageIndex);
      },
    };
  }

  // --- Timeline ---

  const timeline = [];

  timeline.push({
    type: jsPsychBrowserCheck,
    minimum_width: CONFIG.browser.minWidth,
    minimum_height: CONFIG.browser.minHeight,
    inclusion_function: (data) => !data.mobile,
    exclusion_message: (data) => {
      if (data.mobile) {
        return '<p>This experiment requires a desktop or laptop computer. Please return to Prolific and try again on a computer.</p>';
      }
      return '<p>This experiment is not compatible with your browser. Please use Chrome, Firefox, Safari, or Edge.</p>';
    },
    data: { phase: 'browser_check' },
  });

  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: CONSENT_HTML,
    choices: ['y'],
    data: {
      phase: 'consent',
      assignment_id: assignmentId,
    },
  });

  timeline.push({
    type: jsPsychFullscreen,
    fullscreen_mode: true,
    message: '<div style="max-width: 600px; margin: 0 auto; text-align: left;">'
      + '<h2>Welcome!</h2>'
      + '<p>Thank you for participating in this experiment.</p>'
      + '<p>The experiment will now switch to fullscreen mode. '
      + 'For the best experience, please <strong>remain in fullscreen</strong> for the entire experiment.</p>'
      + '<p><strong>Please do not refresh the page or close this tab during the experiment.</strong></p>'
      + '</div>',
    data: { phase: 'fullscreen' },
  });

  // An instruction block: its instructions and comprehension check (repeated after a failure),
  // then the practice preamble, the practice trials and the closing screen. A check failed on
  // its last attempt ends the session, so the nodes after it are skipped (unlessFailed).
  function buildInstructionBlockNodes({
    blockId,
    instructionPages,
    practiceTrials,
    helpBadgePageIndex = null,
  }) {
    const nodes = [];
    nodes.push(buildComprehensionBlock(jsPsych, blockId,
      () => makeInstructionsNode(blockId, instructionPages, { helpBadgePageIndex })));
    nodes.push(unlessFailed([
      buildPracticePreamble(blockId),
      ...practiceTrials,
      buildPostPracticeScreen(blockId),
    ]));
    return nodes;
  }

  // Block 1: the query alone. Its first page is the warning page, so a failed check returns
  // there.
  const warningPages = buildWarningPages();
  const queryContentPages = buildQueryInstructionPages();
  const queryInstructionPages = [...warningPages, ...queryContentPages];
  const helpBadgePageIndex = warningPages.length + queryHelpIntroPageIndex();
  timeline.push(unlessFailed(buildInstructionBlockNodes({
    blockId: 'query',
    instructionPages: queryInstructionPages,
    practiceTrials: buildQueryOnlyPracticeTrials(jsPsych),
    helpBadgePageIndex,
  })));

  // Block 2: the full display, one step.
  const singlehopInstructionPages = buildSinglehopInstructionPages();
  timeline.push(unlessFailed(buildInstructionBlockNodes({
    blockId: 'singlehop',
    instructionPages: singlehopInstructionPages,
    practiceTrials: buildSinglehopPracticeTrials(jsPsych),
  })));

  // Block 3: several steps, with a worked transitive example.
  const multihopInstructionPages = buildMultihopInstructionPages();
  timeline.push(unlessFailed(buildInstructionBlockNodes({
    blockId: 'multihop',
    instructionPages: multihopInstructionPages,
    practiceTrials: buildMultiHopPracticeTrials(jsPsych),
  })));

  // The experiment overview and its comprehension check, then the summary.
  timeline.push(unlessFailed([
    buildComprehensionBlock(jsPsych, 'final',
      () => makeInstructionsNode('final', buildExperimentOverview())),
  ]));

  const summaryMinView = instructionMinViewCallbacks();
  timeline.push(unlessFailed([
    {
      type: jsPsychInstructions,
      pages: buildPreTrainingSummary(),
      show_clickable_nav: true,
      allow_backward: false,
      allow_keys: false,
      button_label_next: 'Proceed to the learning phase',
      data: { phase: 'pre_training_summary' },
      on_load: () => {
        document.body.classList.add('instruction-active');
        summaryMinView.on_load();
      },
      on_finish: () => document.body.classList.remove('instruction-active'),
      on_page_change: summaryMinView.on_page_change,
    },
  ]));

  // The learning phase. The practice blocks used the same trackers; they start afresh here.
  distractorsBetweenTracker.reset();
  queryPairTracker.reset();
  timeline.push(unlessFailed(buildTrainingBlock(jsPsych)));

  // The tests use only the side tracker, which also starts afresh.
  querySideTracker.reset();

  // --- The tests and the questionnaire ---

  const postTrainingNodes = [];

  const transitionMinView = instructionMinViewCallbacks();
  postTrainingNodes.push({
    type: jsPsychInstructions,
    pages: buildTransitionPages(),
    show_clickable_nav: true,
    allow_backward: true,
    allow_keys: false,
    button_label_previous: 'Previous',
    button_label_next: 'Next',
    data: { phase: 'transition' },
    on_load: () => {
      document.body.classList.add('instruction-active');
      transitionMinView.on_load();
    },
    on_finish: () => document.body.classList.remove('instruction-active'),
    on_page_change: transitionMinView.on_page_change,
  });

  const testOrder = [...assignment.test_block_order];

  // The three tests ask about the same 40 rank pairs, so their distance histograms are equal.
  const testRankPairs = generateTestPairHistogram();

  const testBlockBuilders = {
    icl: () => buildICLTestBlock(testRankPairs),
    iwl: () => buildIWLTestBlock(testRankPairs),
    arbitrage: () => buildArbitrageTestBlock(testRankPairs),
  };

  const totalTestTrials = testOrder.length * CONFIG.numTestTrialsPerType;
  let testTrialCount = 0;

  postTrainingNodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: '',
    choices: 'NO_KEYS',
    trial_duration: 0,
    on_load: () => showPhaseProgress('Test phase'),
    data: { phase: 'progress_setup' },
  });

  for (let i = 0; i < testOrder.length; i++) {
    const blockTrials = testBlockBuilders[testOrder[i]]();

    // Points are counted silently during the tests; every arbitrage trial earns one, answered or
    // not.
    const blockType = testOrder[i];
    for (const trial of blockTrials) {
      const origOnFinish = trial.on_finish;
      trial.on_finish = (data) => {
        if (origOnFinish) origOnFinish(data);
        testTrialCount++;
        updatePhaseProgress(testTrialCount, totalTestTrials);
        recordTestPoint(blockType === 'arbitrage' ? true : data.is_correct);
      };
    }

    // A break after every CONFIG.testBreakFrequency trials within a test, and between tests.
    const testBreakFreq = CONFIG.testBreakFrequency;
    const blockStartTrialCount = i * CONFIG.numTestTrialsPerType;
    for (let t = 0; t < blockTrials.length; t++) {
      postTrainingNodes.push(blockTrials[t]);
      const completedInBlock = t + 1;
      if (
        testBreakFreq > 0 &&
        completedInBlock < blockTrials.length &&
        completedInBlock % testBreakFreq === 0
      ) {
        const breakAt = blockStartTrialCount + completedInBlock;
        postTrainingNodes.push(buildBreakNode(
          breakAt,
          totalTestTrials,
          'the test phase',
          false,
          'test',
        ));
      }
    }

    const blockEnd = (i + 1) * CONFIG.numTestTrialsPerType;
    if (i < testOrder.length - 1) {
      postTrainingNodes.push(buildBreakNode(
        blockEnd,
        totalTestTrials,
        'the test phase',
        false,
        'test',
      ));
    }
  }

  postTrainingNodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: '',
    choices: 'NO_KEYS',
    trial_duration: 0,
    on_load: () => removePhaseProgress(),
    data: { phase: 'progress_teardown' },
  });

  postTrainingNodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: '<div class="break-screen" id="perf-summary"></div>',
    choices: [' '],
    data: { phase: 'performance_summary' },
    on_load: () => {
      const pts = getPerformancePoints();
      document.getElementById('perf-summary').innerHTML = `
          <h2>Your Results</h2>
          <p class="points-total">You earned <strong>${pts.total}</strong> points!</p>
          <div class="points-breakdown">
            <div class="points-breakdown-row">
              <span class="points-breakdown-label">Learning phase</span>
              <span class="points-breakdown-value">${pts.training}</span>
            </div>
            <div class="points-breakdown-row">
              <span class="points-breakdown-label">Testing phase</span>
              <span class="points-breakdown-value">${pts.test}</span>
            </div>
          </div>
          <p>Press <kbd>Space</kbd> to continue to a short questionnaire.</p>
        `;
    },
  });

  postTrainingNodes.push(...buildQuestionnaireTrials());

  timeline.push(unlessFailed(postTrainingNodes));

  // --- The end of a completed session: save, then thank the participant ---

  const finalNodes = [];

  finalNodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div style="padding: 2rem; max-width: 600px; margin: 2rem auto; text-align: center;">
        <h2>Saving your data…</h2>
        <p>Please do not close this window.</p>
        <div style="margin: 2rem 0; font-size: 2rem;" aria-label="Loading">⏳</div>
      </div>
    `,
    choices: 'NO_KEYS',
    data: { phase: 'save_data' },
    on_load: () => {
      saveSessionMetadata({
        failed_comprehension: false,
        comprehension_attempts_per_block: { ...comprehensionState.attempts },
        practice_attempts_per_block: { ...practiceState.attempts },
        ...helpGetSessionStats(),
      });
      saveAllData(JSON.parse(jsPsych.data.get().json()));
      experimentFinished = true;
      jsPsych.finishTrial();
    },
  });

  finalNodes.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: THANK_YOU_HTML,
    choices: [' '],
    data: { phase: 'thank_you' },
  });

  timeline.push(unlessFailed(finalNodes));

  // --- The end of a session that failed a comprehension check: save, then stop ---

  timeline.push(ifFailed([
    buildFailedScreenTrial({
      silenceBeforeUnload: () => { experimentFinished = true; },
      finalizeAndSave: () => {
        saveSessionMetadata({
          failed_comprehension: true,
          failed_comprehension_check: failureState.check,
          comprehension_attempts_per_block: { ...comprehensionState.attempts },
          practice_attempts_per_block: { ...practiceState.attempts },
          ...helpGetSessionStats(),
        });
        saveAllData(JSON.parse(jsPsych.data.get().json()));
      },
    }),
  ]));

  jsPsych.data.addProperties({
    assignment_id: assignmentId,
  });

  jsPsych.run(timeline);
}

startExperiment().catch(error => {
  console.error('[Experiment] Fatal error:', error);
  const loadingScreen = document.getElementById('loading-screen');
  if (loadingScreen) loadingScreen.remove();
  document.getElementById('jspsych-target').innerHTML = `
    <div style="padding: 2rem; color: #c0392b; max-width: 700px; margin: 2rem auto; font-family: sans-serif;">
      <h2>Experiment failed to load</h2>
      <p><strong>${error.message}</strong></p>
      <pre style="font-size: 12px; overflow: auto; background: #fdf2f2; padding: 1rem; border-radius: 4px;">${error.stack}</pre>
      <p style="color: #666; font-size: 14px;">Check the browser console (Cmd+Option+J) for more details.</p>
    </div>
  `;
});
