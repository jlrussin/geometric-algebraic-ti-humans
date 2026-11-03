/**
 * The session record and its local save.
 *
 * The record is built in memory while the session runs: the session fields when the stimuli
 * are ready, more session fields as they become known, and one row per screen. When the session
 * ends (completed, or after a failed comprehension check) the record is downloaded as a JSON
 * file named after the assignment and the start time.
 *
 * @module save
 */

import { CONFIG } from './config.js';

/** Phases of the practice, learning and test trials (counted in `total_task_trials`). */
const TASK_PHASES = new Set([
  'practice_query',     'practice_query_extra',
  'practice_singlehop', 'practice_singlehop_extra',
  'practice_multihop',  'practice_multihop_extra',
  'training',
  'test_icl', 'test_iwl', 'test_arbitrage',
]);

let doc = null;
let fileName = null;

/**
 * Start the session record.
 *
 * `stream_offset` is the number of extra values drawn from the seeded generator between the
 * stimulus assignment and the trial build: 0 here. The sessions that were run saved their data
 * over the network while they started, and the network code drew 11, 17 or 19 values from the
 * same generator at that point; the data tables record each session's offset.
 *
 * @param {{assignmentId: number}} params
 */
export function initDataSaving({ assignmentId }) {
  const startTimeISO = new Date().toISOString();
  const stamp = startTimeISO.slice(0, 23).replace(/[-:.]/g, '');
  fileName = `experiment1_a${String(assignmentId).padStart(3, '0')}_${stamp}Z.json`;
  doc = {
    assignment_id: assignmentId,
    stream_offset: 0,
    start_time_iso: startTimeISO,
    is_completed: false,
    config: CONFIG,
    help_open_total_count: 0,
    trials: [],
  };
}

/** Add session fields to the record. */
export function saveSessionMetadata(metadata) {
  Object.assign(doc, metadata);
}

/** Add one row to the record. */
export function saveTrialData(trialData) {
  doc.trials.push(trialData);
}

/**
 * Close the record and download it.
 * @param {object[]} allData - Every row jsPsych holds (`jsPsych.data.get()`).
 */
export function saveAllData(allData) {
  const endTime = new Date().toISOString();
  doc.is_completed = true;
  doc.end_time_iso = endTime;
  doc.total_duration_ms = new Date(endTime) - new Date(doc.start_time_iso);
  doc.total_task_trials = allData.filter(t => TASK_PHASES.has(t.phase)).length;
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Some browsers read the file after the click returns, so the URL is released later.
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
