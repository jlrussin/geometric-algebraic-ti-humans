// Replay one Experiment 2 session: rebuild its questions from its assignment and print one JSON
// object per line for every main question, in session order.
//
//   node experiments/experiment2/replay.mjs --assignment-id N [--code DIR]
//
// The questions are a pure function of the assignment row (assignment_id and condition, from
// data/assignments.json), the configuration (js/config.js) and the item tables
// (data/item_tables.json). The replay makes the startup's own calls: it takes the row with
// resolveAssignmentRow, loads the item tables, checks the configuration against them, and builds
// the session with buildSession (both in js/trial-logic.js), which draws every random choice from
// streams seeded by the assignment_id.
// Each line is the record the session saves with that question, under its saved-row field names,
// plus `schedule_sha256`: the sha256 digest of the whole sequence, which the session document
// records once for the session. The value is the same on every line.
//
// --code DIR runs the experiment in DIR (default: the folder of this script).

import { readFileSync, realpathSync, writeSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

/**
 * Build the session of one assignment and return its main question records in session order,
 * each with the session's `schedule_sha256`.
 * @param {{assignmentId: number, codeDir?: string}} options
 * @returns {Promise<{rows: object[]}>}
 */
export async function replay({ assignmentId, codeDir = HERE }) {
  const root = resolve(codeDir);
  const load = (file) => import(pathToFileURL(join(root, 'js', file)).href);
  const { CONFIG, validateConfig } = await load('config.js');
  const { loadStimuli } = await load('item-tables.js');
  const logic = await load('trial-logic.js');
  for (const name of ['resolveAssignmentRow', 'buildSession']) {
    if (typeof logic[name] !== 'function') {
      throw new Error(`${join(root, 'js', 'trial-logic.js')} does not export ${name}`);
    }
  }
  const { buildSession, resolveAssignmentRow } = logic;

  const { assignments } = JSON.parse(readFileSync(join(root, 'data', 'assignments.json'), 'utf8'));
  // Without an id the startup draws a row at random; the replay always names its row.
  if (assignmentId === null || assignmentId === undefined) {
    throw new Error('replay needs an assignment id');
  }
  const row = resolveAssignmentRow(assignments, assignmentId);

  const { tables } = await loadStimuli();
  validateConfig(CONFIG, tables);
  const session = await buildSession(row, CONFIG, tables);
  const rows = session.main.map((question) => ({
    ...question.record,
    schedule_sha256: session.schedule_sha256,
  }));
  return { rows };
}

function parseArgs(argv) {
  const options = { assignmentId: null, codeDir: HERE };
  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i + 1];
    if (argv[i] === '--assignment-id') options.assignmentId = Number(value);
    else if (argv[i] === '--code') options.codeDir = value;
    else throw new Error(`unknown argument ${argv[i]}`);
    if (value === undefined || value === '' || value.startsWith('--')) {
      throw new Error(`${argv[i]} takes a value`);
    }
    i += 1;
  }
  if (!Number.isInteger(options.assignmentId) || options.assignmentId < 0) {
    throw new Error('--assignment-id takes a non-negative integer');
  }
  return options;
}

// Run when invoked as a script, also through a symbolic link.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { rows } = await replay(parseArgs(process.argv.slice(2)));
    const text = rows.map((row) => JSON.stringify(row)).join('\n') + '\n';
    process.stdout.write(text, () => process.exit(0));
  } catch (error) {
    writeSync(2, `replay: ${error.message}\n`);
    process.exit(1);
  }
}
