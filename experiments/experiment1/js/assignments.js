/**
 * The session's assignment: one row of data/assignments.json. The row sets the order of the
 * ICL and IWL tests, and its `assignment_id` seeds the session's random number generator.
 *
 * @module assignments
 */

import { ASSIGNMENT_ID } from './mode.js';

/**
 * The row the page address names, or a row drawn at random. The draw uses the browser's own
 * generator: it is made before the seeded generator replaces it.
 * @returns {Promise<{assignment_id: number, test_block_order: string[]}>}
 */
export async function chooseAssignment() {
  const response = await fetch('data/assignments.json');
  if (!response.ok) {
    throw new Error(`Failed to fetch data/assignments.json: ${response.status} ${response.statusText}`);
  }
  const { assignments } = await response.json();
  if (ASSIGNMENT_ID === null) {
    return { ...assignments[Math.floor(Math.random() * assignments.length)] };
  }
  const row = assignments.find(r => r.assignment_id === ASSIGNMENT_ID);
  if (!row) throw new Error(`Assignment ${ASSIGNMENT_ID} is not a row of data/assignments.json.`);
  return { ...row };
}
