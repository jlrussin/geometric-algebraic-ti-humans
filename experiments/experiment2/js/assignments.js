/**
 * The session's assignment row, {assignment_id, condition}, from data/assignments.json.
 * `assignment_id` seeds every random stream of the session's questions (js/trial-logic.js); the
 * condition comes from the row.
 *
 * `?assignment=N` (js/mode.js) runs the row whose assignment_id is N; an N that is not a row
 * stops the start-up with an error. Without it a row is drawn uniformly with the browser's
 * Math.random, before the session seeds anything.
 *
 * @module assignments
 */

import { ASSIGNMENT_ID } from './mode.js';
import { resolveAssignmentRow } from './trial-logic.js';

const ASSIGNMENTS_URL = 'data/assignments.json';

/**
 * Load the assignment table and return the session's row.
 * @returns {Promise<{assignment_id: number, condition: string}>}
 */
export async function chooseAssignmentRow() {
  const res = await fetch(ASSIGNMENTS_URL);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${ASSIGNMENTS_URL}: ${res.status} ${res.statusText}`);
  }
  const { assignments } = await res.json();
  const row = resolveAssignmentRow(assignments, ASSIGNMENT_ID, Math.random);
  console.log(`[Assignments] assignment_id ${row.assignment_id}:`, row);
  return row;
}
