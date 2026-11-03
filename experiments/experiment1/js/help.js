/**
 * The help button: a "?" badge in the bottom-left corner that opens a side panel with the
 * rules of the current part of the experiment. It is visible during practice, learning, tests
 * and breaks, and on one instruction page that introduces it; hidden everywhere else.
 *
 * The badge and panel stay on the page for the whole session. experiment.js calls
 * beginTrial(phase) when each screen starts and endTrial() when it ends; endTrial() returns the
 * screen's help statistics, saved on its row:
 *   - help_open_count: times the panel was opened;
 *   - help_open_total_ms: time it was open.
 * getSessionStats() gives help_open_total_count for the session record.
 *
 * @module help
 */

// Phases on which the badge is visible.
const VISIBLE_PHASES = new Set([
  'practice_query', 'practice_query_extra',
  'practice_singlehop', 'practice_singlehop_extra',
  'practice_multihop', 'practice_multihop_extra',
  'training',
  'test_icl', 'test_iwl', 'test_arbitrage',
  'break',
]);

// The badge pulses once, on the first screen of each of these groups of phases (a retry block
// counts with its practice block, and the three tests as one).
const PULSE_KEYS = {
  practice_query: 'practice_query',
  practice_query_extra: 'practice_query',
  practice_singlehop: 'practice_singlehop',
  practice_singlehop_extra: 'practice_singlehop',
  practice_multihop: 'practice_multihop',
  practice_multihop_extra: 'practice_multihop',
  training: 'training',
  test_icl: 'test',
  test_iwl: 'test',
  test_arbitrage: 'test',
};

let mounted = false;
let badge = null;
let panel = null;
let panelHeader = null;
let panelBody = null;
let overlay = null;

let currentPhase = null;
let currentHelpContext = null;
let isPanelVisible = false;
let panelOpenedAt = 0;

// The current screen's statistics.
let trialOpenCount = 0;
let trialOpenAccumMs = 0;
let recordStatsForTrial = true;

// Openings in the whole session.
let sessionTotalCount = 0;

const pulsedKeys = new Set();

// Called once, the first time the panel is opened in the session (onFirstOpen).
const firstOpenListeners = [];


// --- Interface ---

/** Add the badge and the panel to the page (once). */
export function initHelpSystem() {
  if (mounted) return;

  buildDom();
  attachListeners();
  mounted = true;
}

/**
 * Start a screen: reset its statistics, close the panel, and show the badge (with the content
 * for this phase) or hide it.
 *
 * @param {string} phase - The screen's phase.
 * @param {string} [helpContext] - 'training' or 'test': the content shown on a break.
 */
export function beginTrial(phase, helpContext = null) {
  trialOpenCount = 0;
  trialOpenAccumMs = 0;
  // Statistics are saved only for phases where the badge is visible.
  recordStatsForTrial = VISIBLE_PHASES.has(phase);
  currentPhase = phase;
  currentHelpContext = helpContext;

  if (!mounted) return;

  if (isPanelVisible) hidePanel({ silent: true });

  if (VISIBLE_PHASES.has(phase)) {
    badge.style.display = '';
    renderPanelContent();
    const pulseKey = PULSE_KEYS[phase];
    if (pulseKey && !pulsedKeys.has(pulseKey)) {
      pulsedKeys.add(pulseKey);
      pulse();
    }
  } else {
    badge.style.display = 'none';
  }
}

/**
 * End a screen.
 * @returns {object} {help_open_count, help_open_total_ms}, or {} for a phase without the badge.
 */
export function endTrial() {
  // A panel still open: count its time so far (the next screen closes it).
  if (mounted && isPanelVisible) {
    trialOpenAccumMs += performance.now() - panelOpenedAt;
    panelOpenedAt = performance.now();
  }
  if (!recordStatsForTrial) return {};
  return {
    help_open_count: trialOpenCount,
    help_open_total_ms: Math.round(trialOpenAccumMs),
  };
}

/** @returns {{help_open_total_count: number}} */
export function getSessionStats() {
  return { help_open_total_count: sessionTotalCount };
}

/** @returns {boolean} Whether the panel has been opened in this session. */
export function hasOpenedHelp() {
  if (!mounted) return true;
  return sessionTotalCount > 0;
}

/**
 * Call `cb` the first time the panel is opened (at once, on the next microtask, if it already
 * was).
 * @param {Function} cb
 */
export function onFirstOpen(cb) {
  if (!mounted) return;
  if (typeof cb !== 'function') return;
  if (sessionTotalCount > 0) {
    Promise.resolve().then(cb);
    return;
  }
  firstOpenListeners.push(cb);
}

/**
 * Show or hide the badge regardless of the phase (the instruction page that introduces it).
 * The next beginTrial() decides again.
 * @param {boolean} visible
 */
export function setBadgeVisible(visible) {
  if (!mounted || !badge) return;
  badge.style.display = visible ? '' : 'none';
}


// --- Page elements ---

function buildDom() {
  // A transparent overlay; a click on it closes the panel.
  overlay = document.createElement('div');
  overlay.className = 'help-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  document.body.appendChild(overlay);

  panel = document.createElement('aside');
  panel.className = 'help-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Help and tips');
  panel.setAttribute('aria-hidden', 'true');

  const closeBtn = document.createElement('button');
  closeBtn.className = 'help-panel-close';
  closeBtn.setAttribute('aria-label', 'Close help');
  closeBtn.type = 'button';
  closeBtn.textContent = '×';

  panelHeader = document.createElement('div');
  panelHeader.className = 'help-panel-header';
  panelHeader.textContent = 'Tips';

  panelBody = document.createElement('div');
  panelBody.className = 'help-panel-body';

  panel.appendChild(closeBtn);
  panel.appendChild(panelHeader);
  panel.appendChild(panelBody);
  document.body.appendChild(panel);

  badge = document.createElement('button');
  badge.className = 'help-badge';
  badge.type = 'button';
  badge.setAttribute('aria-label', 'Help and tips');
  badge.textContent = '?';
  badge.style.display = 'none';
  document.body.appendChild(badge);

  panel._closeBtn = closeBtn;
}

function attachListeners() {
  badge.addEventListener('click', toggle);
  overlay.addEventListener('click', () => hidePanel());
  panel._closeBtn.addEventListener('click', () => hidePanel());

  const escHandler = (e) => {
    if (e.key === 'Escape' && isPanelVisible) hidePanel();
  };
  document.addEventListener('keydown', escHandler);
}


// --- Opening and closing ---

function toggle() {
  if (isPanelVisible) hidePanel();
  else showPanel();
}

function showPanel() {
  if (!mounted || isPanelVisible) return;
  renderPanelContent();
  panel.classList.add('visible');
  overlay.classList.add('visible');
  panel.setAttribute('aria-hidden', 'false');
  overlay.setAttribute('aria-hidden', 'false');
  isPanelVisible = true;
  panelOpenedAt = performance.now();
  trialOpenCount += 1;
  sessionTotalCount += 1;
  if (sessionTotalCount === 1 && firstOpenListeners.length > 0) {
    const pending = firstOpenListeners.splice(0);
    for (const cb of pending) {
      try { cb(); } catch (e) { console.error('[Help] onFirstOpen listener threw:', e); }
    }
  }
}

/**
 * @param {object} [opts]
 * @param {boolean} [opts.silent=false] - Closed because a new screen began; its time was
 *   already counted by endTrial().
 */
function hidePanel({ silent = false } = {}) {
  if (!mounted || !isPanelVisible) return;
  panel.classList.remove('visible');
  overlay.classList.remove('visible');
  panel.setAttribute('aria-hidden', 'true');
  overlay.setAttribute('aria-hidden', 'true');
  isPanelVisible = false;
  if (!silent) {
    trialOpenAccumMs += performance.now() - panelOpenedAt;
  }
}

function pulse() {
  if (!badge) return;
  badge.classList.remove('pulsing');
  // Reading offsetWidth forces a reflow, so the animation starts again.
  void badge.offsetWidth;
  badge.classList.add('pulsing');
}


// --- Content ---

/** The content for the current screen; on a break, its helpContext decides. */
function getContentKey() {
  if (currentHelpContext === 'training') return 'training';
  if (currentHelpContext === 'test') return 'test';
  if (currentPhase === 'training') return 'training';
  if (typeof currentPhase === 'string') {
    if (currentPhase.startsWith('practice_query')) return 'practice_query';
    if (currentPhase.startsWith('practice_singlehop')) return 'practice_singlehop';
    if (currentPhase.startsWith('practice_multihop')) return 'practice_multihop';
    if (currentPhase.startsWith('test_')) return 'test';
    // The instruction page that introduces the button previews the content of block 1.
    if (currentPhase === 'instructions_query') return 'practice_query';
  }
  return 'training';
}

function renderPanelContent() {
  const key = getContentKey();
  panelBody.innerHTML = CONTENT_BUILDERS[key]() + META_TIP_HTML;
}

const CLUE_READING =
  'The arrow in each clue points to the preferred object, and the preferred object is on top.';

const MASKED_TIP = 'When the clues show gray boxes, rely on what you\'ve learned.';

const SECTION = (title, body) => `
  <section class="help-section">
    <h3>${title}</h3>
    ${body}
  </section>`;

const WORKED_EXAMPLE = `
  <div class="help-example">
    Clue 1: A over B<br>
    Clue 2: B over C<br>
    → <strong>The aliens prefer A over C</strong>
  </div>`;

const META_TIP_HTML = `
  <p class="help-meta-tip">Note: tips change as you progress through the experiment.</p>`;

const CONTENT_BUILDERS = {
  practice_query: () => [
    SECTION('What to do', '<p>Pick the object the aliens prefer more.</p>'),
    SECTION('Controls', '<p><kbd>F</kbd> = left, <kbd>J</kbd> = right</p>'),
    SECTION('Tip', '<p>You won\'t know which they prefer at first — use the feedback after each answer to learn their preferences.</p>'),
  ].join(''),

  practice_singlehop: () => [
    SECTION('What to do', '<p>Pick the object the aliens prefer more.</p>'),
    SECTION('Controls', '<p><kbd>F</kbd> = left, <kbd>J</kbd> = right</p>'),
    SECTION('Reading clues', `<p>${CLUE_READING}</p>`),
    SECTION('Tip', '<p>The clues are there to help, but you don\'t always need them. If you already know the answer, you can just answer.</p>'),
  ].join(''),

  practice_multihop: () => [
    SECTION('What to do', '<p>Pick the object the aliens prefer more.</p>'),
    SECTION('Controls', '<p><kbd>F</kbd> = left, <kbd>J</kbd> = right</p>'),
    SECTION('Reading clues', `<p>${CLUE_READING}</p>`),
    SECTION('Combining clues', `<p>Sometimes one clue isn't enough. For example:</p>${WORKED_EXAMPLE}`),
    SECTION('Tip', '<p>Look for the clues that connect the two objects in the question — sometimes you\'ll need to combine more than two.</p>'),
  ].join(''),

  training: () => {
    const tips = [
      '<li>Look for the clues that connect the two objects in the question — sometimes you\'ll need to combine more than two.</li>',
      '<li>The clues can help, but if you already know the answer, you can just answer.</li>',
      `<li>${MASKED_TIP}</li>`,
    ];
    return [
      SECTION('What to do', '<p>Pick the object the aliens prefer more.</p>'),
      SECTION('Reading clues', `<p>${CLUE_READING}</p>`),
      SECTION('Combining clues', `<p>Sometimes one clue isn't enough. For example:</p>${WORKED_EXAMPLE}`),
      SECTION('Tips', `<ul>${tips.join('')}</ul>`),
    ].join('');
  },

  test: () => {
    const diffBullets = [
      '<li>No feedback after answers</li>',
      '<li>Feedback timing is fixed — it doesn\'t tell you if you were correct</li>',
      '<li>You may see new images you haven\'t seen before</li>',
    ];
    const tips = [
      `<li>${MASKED_TIP}</li>`,
      '<li>Answer as quickly and as accurately as possible.</li>',
    ];
    return [
      SECTION('What to do', '<p>Pick the object the aliens prefer more.</p>'),
      SECTION('What\'s different in the test', `<ul>${diffBullets.join('')}</ul>`),
      SECTION('Tips', `<ul>${tips.join('')}</ul>`),
    ].join('');
  },
};
