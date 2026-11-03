/**
 * The session's data document and its download at the end of the session.
 *
 * One document per session, created when the participant agrees to the consent form. Rows and
 * session fields recorded before consent (the browser-check row, the summary of the session's
 * questions) are held and written into the document when it is created; if consent is declined,
 * nothing is kept. Every later row is appended as it finishes. At the end, `saveAllData`
 * completes the document and downloads it as `<file_prefix>.json`.
 *
 * `buildInitialDocument`, `globalTrialProperties`, `finalizeTrialRow` and `planMetadata` build
 * the document root and the rows; they use no browser API.
 *
 * @module save
 */

import { CONFIG } from './config.js';

/** The phase of question rows; `total_task_trials` counts them at the end of the session. */
export const TASK_PHASES = new Set(['main']);

// --- Document and rows ---------------------------------------------------------------

/**
 * The file name (without `.json`):
 * `{YYYY-MM-DD}_{HHMMSSmmm}Z_{condition}_a{assignment_id}_{tail}`, with `tail` a random
 * 6-character token so that two sessions never share a name.
 */
function buildFilePrefix(assignmentId, condition, now, randomTail) {
  const iso = now.toISOString();
  const date = iso.slice(0, 10);
  const time = iso.slice(11, 23).replace(/[:.]/g, '');
  const paddedId = String(assignmentId).padStart(3, '0');
  return `${date}_${time}Z_${condition}_a${paddedId}_${randomTail}`;
}

/**
 * Throw unless the condition is set: a document or row without it could not be analyzed or
 * regenerated.
 * @param {object} o - Has `condition`.
 */
function requireCondition(o) {
  if (typeof o.condition !== 'string' || o.condition === '') {
    throw new Error(`[save] condition is required (the assignment row's value); got ${JSON.stringify(o.condition)}.`);
  }
}

/**
 * The document root written at consent.
 * @param {object} o
 * @param {number} o.assignmentId
 * @param {string} o.condition - The assignment row's `condition`.
 * @param {object} o.config - The configuration (CONFIG).
 * @param {Date} o.now - The time of consent: `start_time_iso`, and the start of
 *   `total_duration_ms` (saveAllData).
 * @param {string} o.randomTail - The file name's 6-character token.
 * @returns {object}
 */
export function buildInitialDocument(o) {
  requireCondition(o);
  return {
    assignment_id: o.assignmentId,
    condition: o.condition,
    file_prefix: buildFilePrefix(o.assignmentId, o.condition, o.now, o.randomTail),
    start_time_iso: o.now.toISOString(),
    consent_given: true,
    is_completed: false,
    config: JSON.parse(JSON.stringify(o.config)),
    trials: [],
  };
}

/**
 * The fields on every row (jsPsych addProperties).
 * @param {{assignmentId: number, condition: string}} o
 * @returns {object}
 */
export function globalTrialProperties(o) {
  requireCondition(o);
  return {
    assignment_id: o.assignmentId,
    condition: o.condition,
  };
}

/** The page's screen size and pixel ratio, or null outside a browser. */
function pageScreen() {
  if (typeof window === 'undefined' || !window.screen) return null;
  return { width: window.screen.width, height: window.screen.height, devicePixelRatio: window.devicePixelRatio };
}

/** Browser-check fields moved to the document root (`browser_metadata`). */
const BROWSER_CHECK_FIELDS = [
  'browser', 'browser_version', 'os', 'mobile', 'width', 'height',
  'window_width', 'window_height', 'screen_width', 'screen_height',
  'device_pixel_ratio', 'vsync_rate', 'fullscreen', 'microphone', 'webaudio', 'webcam',
];

/**
 * Tidy a finished row (jsPsych's `on_trial_finish`), in place:
 *   - `interaction_events_json` = the blur/focus/fullscreen events that fired during this trial
 *     ({event, time_ms} maps, as JSON); on question rows also `n_blur_events`, the number of
 *     'blur' events;
 *   - drops `internal_node_id`, `plugin_version`, `stimulus`, `message` and `pages` (the
 *     screens' HTML);
 *   - survey rows: `response` (an object) becomes `response_json`, without SurveyJS's
 *     `progress_*` entries;
 *   - browser-check rows: the browser fields leave the row and are returned as
 *     `browser_metadata` for the document root. The browser-check plugin measures no screen
 *     size or pixel ratio, so those come from `screen` (window.screen and
 *     window.devicePixelRatio in the browser).
 *
 * @param {object} data - The jsPsych row (changed in place).
 * @param {Array<{event: string, time_ms: number}>} [events=[]]
 * @param {?{width: number, height: number, devicePixelRatio: number}} [screen]
 *   Defaults to the page's window.screen and window.devicePixelRatio (null in Node).
 * @returns {{browser_metadata: ?object}}
 */
export function finalizeTrialRow(data, events = [], screen = pageScreen()) {
  data.interaction_events_json = JSON.stringify(events);
  if (data.trial_type === 'question-trial') {
    data.n_blur_events = events.filter((e) => e.event === 'blur').length;
  }
  delete data.internal_node_id;
  delete data.plugin_version;

  if (data.trial_type === 'survey' && data.response && typeof data.response === 'object') {
    const filtered = {};
    for (const [k, v] of Object.entries(data.response)) {
      if (!k.startsWith('progress_')) filtered[k] = v;
    }
    data.response_json = JSON.stringify(filtered);
    delete data.response;
  }

  let browser_metadata = null;
  if (data.trial_type === 'browser-check') {
    browser_metadata = {
      browser: data.browser ?? null,
      browser_version: data.browser_version ?? null,
      os: data.os ?? null,
      is_mobile: data.mobile ?? null,
      window_width_px: data.width ?? data.window_width ?? null,
      window_height_px: data.height ?? data.window_height ?? null,
      screen_width_px: data.screen_width ?? (screen ? screen.width : null),
      screen_height_px: data.screen_height ?? (screen ? screen.height : null),
      device_pixel_ratio: data.device_pixel_ratio ?? (screen ? screen.devicePixelRatio : null),
      vsync_rate_hz: data.vsync_rate ?? null,
    };
    for (const k of BROWSER_CHECK_FIELDS) delete data[k];
  }

  delete data.stimulus;
  delete data.message;
  delete data.pages;
  return { browser_metadata };
}

/**
 * The summary of `buildSession`'s result, for the document root. The questions themselves are
 * not saved here: every question's record is in its row, replay.mjs rebuilds them from
 * `assignment_id` and `condition`, and `schedule_sha256` identifies them.
 * @param {object} session - trial-logic `buildSession` result.
 * @returns {object}
 */
export function planMetadata(session) {
  return {
    item_table_version: session.item_table_version,
    item_table_hash: session.item_table_hash,
    schedule_sha256: session.schedule_sha256,
    balance_exactness: session.balance_exactness,
    generation_stats: session.generation_stats,
  };
}

// --- The session's document -------------------------------------------------------

/** The document, from consent on; null before. */
let sessionDoc = null;
/** Written into the document when it is created (nothing is kept before consent). */
const preConsentTrials = [];
const preConsentMetadata = {};

/** A 6-character token [0-9a-z] for the file name, from crypto.getRandomValues. */
function randomTail() {
  const alphabet = '0123456789abcdefghijklmnopqrstuvwxyz';
  const bytes = new Uint8Array(6);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

/**
 * Create the document. Call once, when the participant agrees to the consent form. Rows and
 * fields saved earlier in the session are written into it.
 * @param {{assignmentId: number, condition: string}} params
 */
export function initDataSaving({ assignmentId, condition }) {
  if (sessionDoc) return;
  sessionDoc = buildInitialDocument({
    assignmentId,
    condition,
    config: CONFIG,
    now: new Date(),
    randomTail: randomTail(),
  });
  Object.assign(sessionDoc, preConsentMetadata);
  sessionDoc.trials = preConsentTrials.splice(0);
}

/**
 * Merge fields into the document root (held until consent).
 * @param {object} metadata
 */
export function saveSessionMetadata(metadata) {
  if (!sessionDoc) {
    Object.assign(preConsentMetadata, metadata);
    return;
  }
  Object.assign(sessionDoc, metadata);
}

/**
 * Append one row (from jsPsych's `on_trial_finish`, after `finalizeTrialRow`); held until
 * consent.
 * @param {object} trialData
 */
export function saveTrialData(trialData) {
  if (!sessionDoc) {
    preConsentTrials.push(trialData);
    return;
  }
  sessionDoc.trials.push(trialData);
}

/** A new object URL of the document as JSON. */
function recordUrl() {
  const blob = new Blob([JSON.stringify(sessionDoc, null, 2)], { type: 'application/json' });
  return URL.createObjectURL(blob);
}

/**
 * Download the document as `fileName`. The link is added to the page for the click and its URL
 * is revoked a minute later: some browsers ignore a click on a link outside the page or cancel a
 * download whose URL is revoked at once.
 * @param {string} fileName
 */
function downloadRecord(fileName) {
  const url = recordUrl();
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

/**
 * The end-of-session save: `is_completed`, `end_time_iso`, `total_duration_ms` (from
 * `start_time_iso`, the moment of consent, to `end_time_iso`) and `total_task_trials` (rows
 * whose phase is in TASK_PHASES), then the document is downloaded as `<file_prefix>.json`.
 * @param {object[]} allData - `JSON.parse(jsPsych.data.get().json())`.
 * @returns {Promise<?{fileName: string, url: string}>} The file name, and an object URL of the
 *   document for a link that downloads it again (kept for the rest of the page's life); null
 *   before consent.
 */
export async function saveAllData(allData) {
  if (!sessionDoc) {
    console.warn('[save] saveAllData was called before consent; nothing saved.');
    return null;
  }
  const endTime = new Date().toISOString();
  Object.assign(sessionDoc, {
    is_completed: true,
    end_time_iso: endTime,
    total_duration_ms: new Date(endTime) - new Date(sessionDoc.start_time_iso),
    total_task_trials: allData.filter((t) => TASK_PHASES.has(t.phase)).length,
  });
  const fileName = `${sessionDoc.file_prefix}.json`;
  downloadRecord(fileName);
  console.log(`[save] Downloaded ${fileName} (${sessionDoc.trials.length} rows)`);
  return { fileName, url: recordUrl() };
}
