/**
 * The seeded random number generator: mulberry32, seeded from a string hash, installed as
 * Math.random so that every draw of the session comes from one reproducible stream.
 *
 * @module seeded-rng
 */

/**
 * Hash a string to a 32-bit unsigned integer: the cyrb53 hash's second 32-bit state word (h2).
 *
 * @param {string} str - Input string (the session's assignment_id).
 * @param {number} [seed=0] - Seed of the hash.
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
  return (h2 >>> 0);
}

/**
 * A mulberry32 generator: a function returning floats in [0, 1), like Math.random.
 *
 * @param {number} seed - 32-bit seed.
 * @returns {function(): number}
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
 * Replace Math.random by a mulberry32 generator with this seed.
 * @param {number} seed - 32-bit seed.
 */
export function installSeededRandom(seed) {
  Math.random = mulberry32(seed);
}
