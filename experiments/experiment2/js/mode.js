/**
 * The page's one URL parameter. `?assignment=N` runs row N of data/assignments.json
 * (js/assignments.js); without it, or in Node, ASSIGNMENT_ID is null and a row is drawn at
 * random. A value that is not a row number stops the start-up with an error.
 *
 * @module mode
 */

const urlParams = new URLSearchParams(
  (typeof window !== 'undefined' && window.location) ? window.location.search : '',
);

/** The requested assignment row, or null when the address names none. */
export const ASSIGNMENT_ID = (() => {
  const raw = urlParams.get('assignment');
  if (raw === null) return null;
  if (!/^\d+$/.test(raw)) throw new Error(`?assignment must be a row number; got "${raw}".`);
  return Number(raw);
})();
