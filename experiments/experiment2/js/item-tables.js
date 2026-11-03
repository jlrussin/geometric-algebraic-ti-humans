/**
 * Load the item tables (data/item_tables.json) and check their structure.
 *
 * Works in the browser (fetch, paths relative to the experiment folder, i.e. index.html) and in
 * Node (fs, the same relative paths resolved against the experiment folder; absolute paths are
 * read as given).
 *
 * The structural checks (shapes and types of the fields the experiment reads) live here; the
 * checks against the configuration (domains, version, capacity, the instruction example) are
 * validateConfig's (js/config.js).
 *
 * @module item-tables
 */

/**
 * The item tables' path, relative to the experiment folder. When the table file changes,
 * CONFIG.itemTableVersion must follow (validateConfig rule 7).
 */
export const STIMULUS_PATHS = {
  itemTables: 'data/item_tables.json',
};

const IS_NODE = typeof window === 'undefined'
  && typeof process !== 'undefined' && process.versions != null && process.versions.node != null;

async function readJson(path) {
  if (IS_NODE) {
    const { readFile } = await import('node:fs/promises');
    const url = path.startsWith('/') ? path : new URL(`../${path}`, import.meta.url);
    return JSON.parse(await readFile(url, 'utf8'));
  }
  const res = await fetch(path);
  if (!res.ok) throw new Error(`[item-tables] Failed to fetch ${path}: ${res.status} ${res.statusText}`);
  return res.json();
}

function assertShape(cond, msg) {
  if (!cond) throw new Error(`[item-tables] ${msg}`);
}

function checkTables(tables, path) {
  assertShape(tables && typeof tables === 'object', `${path}: not a JSON object.`);
  assertShape(typeof tables.table_version === 'string' && tables.table_version, `${path}: missing table_version.`);
  assertShape(Array.isArray(tables.domains) && tables.domains.length > 0, `${path}: missing domains.`);
  const seenDomains = new Set();
  for (const dom of tables.domains) {
    const id = dom && dom.domain_id;
    assertShape(typeof id === 'string' && !seenDomains.has(id), `${path}: bad or duplicate domain_id '${id}'.`);
    seenDomains.add(id);
    for (const k of ['relation_phrase', 'query_phrase', 'query_emphasis']) {
      assertShape(typeof dom[k] === 'string' && dom[k].length > 0, `${path}: domain '${id}' is missing ${k}.`);
    }
    assertShape(dom.query_phrase.includes(dom.query_emphasis), `${path}: domain '${id}': query_emphasis must occur in query_phrase.`);
    assertShape(dom.slot_tables && typeof dom.slot_tables === 'object', `${path}: domain '${id}' has no slot_tables.`);
    assertShape(Array.isArray(dom.forbidden_adjacent_pairs)
      && dom.forbidden_adjacent_pairs.every((p) => Array.isArray(p) && p.length === 2 && p.every((x) => typeof x === 'string')),
    `${path}: domain '${id}': forbidden_adjacent_pairs must be an array of item-ID pairs.`);
    for (const [n, slots] of Object.entries(dom.slot_tables)) {
      // Skip a table that is not an array of slot objects.
      if (!Array.isArray(slots) || slots.some((s) => typeof s !== 'object')) continue;
      const ids = new Set();
      for (const s of slots) {
        assertShape(Number.isInteger(s.slot) && Array.isArray(s.items), `${path}: domain '${id}' table ${n}: bad slot entry.`);
        for (const it of s.items) {
          assertShape(typeof it.item_id === 'string' && !ids.has(it.item_id), `${path}: domain '${id}' table ${n}: bad or duplicate item_id '${it.item_id}'.`);
          ids.add(it.item_id);
          assertShape(typeof it.name === 'string' && it.name.length > 0, `${path}: item '${it.item_id}' has no name.`);
          assertShape(typeof it.article === 'string', `${path}: item '${it.item_id}': article must be a string ("" for none).`);
          assertShape(Number.isInteger(it.name_chars) && it.name_chars === it.name.length, `${path}: item '${it.item_id}': name_chars must equal the name's length.`);
          assertShape(typeof it.magnitude === 'number', `${path}: item '${it.item_id}' has no numeric magnitude.`);
          assertShape(typeof it.eligible === 'boolean', `${path}: item '${it.item_id}': eligible must be a boolean.`);
        }
      }
    }
  }
}

/**
 * Load and structurally validate the item tables.
 *
 * @param {{itemTables: string}} [paths=STIMULUS_PATHS]
 * @returns {Promise<{tables: object}>}
 */
export async function loadStimuli(paths = STIMULUS_PATHS) {
  const tables = await readJson(paths.itemTables);
  checkTables(tables, paths.itemTables);
  return { tables };
}
