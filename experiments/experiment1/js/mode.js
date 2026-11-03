/**
 * The page address. `?assignment=N` runs row N of data/assignments.json; without the parameter
 * a row is drawn at random.
 *
 * @module mode
 */

const params = new URLSearchParams(window.location.search);

/** The requested assignment row, or null when the address names none. */
export const ASSIGNMENT_ID = (() => {
  const raw = params.get('assignment');
  if (raw === null) return null;
  if (!/^\d+$/.test(raw)) throw new Error(`?assignment must be a row number; got "${raw}".`);
  return Number(raw);
})();
