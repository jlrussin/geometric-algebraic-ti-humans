/**
 * Seeded random numbers.
 *
 * Provides mulberry32 (a fast, well-distributed 32-bit generator), a string-to-seed hash, and
 * `makeStream`, which gives every stage of the question generation its own independent stream
 * (js/trial-logic.js). The experiment also seeds the global Math.random from
 * hashString(String(assignment_id)) for incidental use; the question generation never uses
 * Math.random.
 *
 * @module seeded-rng
 */

/**
 * Hash a string to a 32-bit integer using cyrb53 (truncated to 32 bits).
 * Deterministic: same string always produces the same hash.
 *
 * @param {string} str - Input string.
 * @param {number} [seed=0] - Optional seed for the hash.
 * @returns {number} 32-bit unsigned integer.
 */
export function hashString(str, seed = 0) {
  let h1 = 0xdeadbeef ^ seed;
  let h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  // Combine into a single 32-bit value
  return (h2 >>> 0);
}

/**
 * Create a mulberry32 PRNG function from a 32-bit seed.
 * Returns a function that produces floats in [0, 1) on each call,
 * matching the interface of Math.random().
 *
 * @param {number} seed - 32-bit seed.
 * @returns {function(): number} PRNG function.
 */
export function mulberry32(seed) {
  let state = seed | 0;
  return function () {
    state |= 0;
    state = (state + 0x6D2B79F5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Install a seeded PRNG as Math.random. Returns a restore function.
 *
 * @param {number} seed - 32-bit seed.
 * @returns {{ restore: function, rng: function }} restore() reinstates
 *   the original Math.random; rng is the seeded function.
 */
export function installSeededRandom(seed) {
  const original = Math.random;
  const rng = mulberry32(seed);
  Math.random = rng;
  return {
    restore: () => { Math.random = original; },
    rng,
  };
}

/**
 * One independent random stream per stage of the question generation:
 * mulberry32(hashString(`${assignmentId}:${label}`)). Changing the draws of one stage never
 * changes another stage's draws. Retry streams use the label suffix `:retry<n>` (e.g.
 * 'sequence:retry1').
 *
 * @param {number|string} assignmentId - The session's assignment_id.
 * @param {string} label - Stream label (the stages are listed in js/trial-logic.js).
 * @returns {function(): number} PRNG producing floats in [0, 1).
 */
export function makeStream(assignmentId, label) {
  return mulberry32(hashString(`${assignmentId}:${label}`));
}
