// Replay one Experiment 1 session: rebuild its trial sequence from its assignment and print one
// JSON object per line for every task trial, in session order.
//
//   node experiments/experiment1/replay.mjs --assignment-id N [--stream-offset K] [--code DIR]
//
// The experiment's own startup (js/experiment.js) runs in Node, opened at the page address
// ?assignment=N, with small stand-ins for the browser and for the libraries the page loads from
// the network (jsPsych and its plugins, each defined under the global name the page uses). The
// startup seeds the random stream from the assignment and builds the whole timeline before the
// first screen; the replay keeps that timeline. It then runs the experiment's own trial plugin on
// every task trial, with no response and a simulated clock, so each line is the row that plugin
// saves for the trial (plus the trial's data parameter): the design fields as the participant saw
// them, and the response fields of a trial left unanswered (`response` null, `is_timed_out` true).
// The fields jsPsych adds to every row, such as `trial_index`, are not included.
//
// The retry block of each practice block appears once, after the block; a session shows it zero
// to two times.
//
// --stream-offset K: the sessions saved data over the network while the experiment was starting,
// and that network code drew K numbers from the same seeded stream (K was 11, 17 or 19), after the
// stimuli were drawn and before the practice blocks were built. The replay draws K numbers at that
// point: the first time the startup waits (for the images to load) after it has begun to draw
// from the seeded stream. The replay reports on stderr how many numbers the startup had drawn by
// then, which identifies that point in the seeded stream.
//
// --code DIR runs the experiment in DIR (default: the folder of this script).

import { readFile } from 'node:fs/promises';
import { readFileSync, realpathSync, writeSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

// --- Stand-ins ---------------------------------------------------------------------------------

// An object that accepts any property access, assignment, call or construction and returns
// another such object; it stands in for the DOM and for the jsPsych library.
function inert() {
  const values = new Map();
  return new Proxy(function () {}, {
    get(_target, key) {
      if (key === 'then') return undefined;
      if (key === Symbol.toPrimitive) return (hint) => (hint === 'number' ? NaN : '');
      if (key === Symbol.iterator) return function* () {};
      if (!values.has(key)) values.set(key, inert());
      return values.get(key);
    },
    set(_target, key, value) {
      values.set(key, value);
      return true;
    },
    apply: () => inert(),
    construct: () => inert(),
  });
}

// The global names under which the page's network libraries define themselves: `jsPsychModule`
// for jsPsych and `jsPsych<Name>` for each plugin `@jspsych/plugin-<name>`. Other network scripts
// get no stand-in.
function libraryGlobals(indexHtml) {
  const names = [];
  for (const [, src] of indexHtml.matchAll(/<script[^>]*\bsrc="(https:[^"]+)"/g)) {
    const plugin = src.match(/@jspsych\/plugin-([a-z-]+)@/);
    if (plugin) {
      names.push('jsPsych' + plugin[1].replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase()));
    } else if (/\/jspsych@/.test(src)) {
      names.push('jsPsychModule');
    }
  }
  return names;
}

// --- Replay ------------------------------------------------------------------------------------

/**
 * Run the experiment's startup for one assignment. Returns the saved-row record of every task
 * trial in session order, and the number of draws the startup had made from its seeded stream
 * when the offset draws were made (null if the startup never waited after it began drawing). The
 * experiment's modules keep their state, so call this once per process.
 * @param {{assignmentId: number, streamOffset?: number, codeDir?: string}} options
 * @returns {Promise<{rows: object[], drawsBeforeOffset: ?number}>}
 */
export async function replay({ assignmentId, streamOffset = 0, codeDir = HERE }) {
  const root = resolve(codeDir);
  let clock = 0;

  // The browser.
  globalThis.window = globalThis;
  const search = `?assignment=${assignmentId}`;
  globalThis.location = { search, href: `index.html${search}` };
  globalThis.document = inert();
  globalThis.screen = { width: 1280, height: 800 };
  Object.assign(globalThis, {
    innerWidth: 1280,
    innerHeight: 800,
    devicePixelRatio: 1,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  });
  const storage = new Map();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
      clear: () => storage.clear(),
    },
  });
  Object.defineProperty(globalThis, 'performance', {
    configurable: true,
    writable: true,
    value: { now: () => clock },
  });
  // Network requests complete on a later turn of the event loop, as in a browser.
  const later = () => new Promise((done) => setTimeout(done, 0));
  globalThis.fetch = async (url) => {
    await later();
    try {
      return new Response(await readFile(join(root, String(url))), { status: 200 });
    } catch {
      return new Response(null, { status: 404, statusText: 'Not Found' });
    }
  };
  // Images load on a later turn of the event loop, as in a browser; no file is read.
  globalThis.Image = class {
    set src(value) {
      this.source = value;
      setTimeout(() => this.onload?.(), 0);
    }

    get src() {
      return this.source;
    }
  };
  // The experiment's messages would mix with the rows on stdout; warnings and errors go to stderr.
  console.log = console.info = console.debug = () => {};

  // The libraries. jsPsych's `run` receives the finished timeline.
  let timeline;
  let finished;
  const timelineReady = new Promise((done) => { finished = done; });
  const libraries = new Set();
  for (const name of libraryGlobals(readFileSync(join(root, 'index.html'), 'utf8'))) {
    const library = inert();
    libraries.add(library);
    globalThis[name] = library;
  }
  globalThis.initJsPsych = () => {
    const jsPsych = inert();
    jsPsych.run = (nodes) => {
      finished(nodes);
      return Promise.resolve();
    };
    return jsPsych;
  };

  // The seeded stream: the page installs its generator as Math.random. Draws from it are counted;
  // the first one schedules the offset draws for the next turn of the event loop, so they come at
  // the first wait after the startup has begun to use the stream.
  const native = Math.random;
  let seeded = null;
  let draws = 0;
  let drawsBeforeOffset = null;
  const drawOffset = () => {
    if (timeline !== undefined) return;
    drawsBeforeOffset = draws;
    for (let i = 0; i < streamOffset; i += 1) seeded();
  };
  const counted = () => {
    draws += 1;
    if (draws === 1) setTimeout(drawOffset, 0);
    return seeded();
  };
  Object.defineProperty(Math, 'random', {
    configurable: true,
    get: () => (seeded ? counted : native),
    set: (generator) => {
      seeded = generator;
    },
  });

  // Run the startup until it hands its timeline to jsPsych.
  process.once('beforeExit', () => finished(null));
  await import(pathToFileURL(join(root, 'js', 'experiment.js')).href);
  timeline = await timelineReady;
  if (!timeline) throw new Error('the experiment stopped before it built its timeline');
  if (seeded === null) throw new Error('the experiment never installed a seeded random stream');
  if (streamOffset > 0 && draws === 0) {
    throw new Error('the experiment never drew from its seeded random stream');
  }
  if (streamOffset > 0 && drawsBeforeOffset === null) {
    throw new Error('the experiment did not wait after it began to draw from its seeded stream');
  }

  // The task trials: every trial whose plugin is part of the experiment's own code.
  const isTask = (type) => typeof type === 'function' && !libraries.has(type) && 'info' in type;
  const tasks = [];
  const walk = (nodes) => {
    for (const node of nodes) {
      if (Array.isArray(node.timeline)) walk(node.timeline);
      else if (isTask(node.type)) tasks.push(node);
    }
  };
  walk(timeline);

  // Each trial runs in its plugin: parameters not set on the node take the plugin's defaults, as in
  // jsPsych, and the plugin's timers run on the simulated clock until it saves its row.
  const rows = tasks.map((node) => {
    const Plugin = node.type;
    const trial = {};
    for (const [name, spec] of Object.entries(Plugin.info.parameters)) {
      trial[name] = name in node ? node[name] : spec.default;
    }
    let row = null;
    let timers = [];
    let order = 0;
    clock = 0;
    const jsPsych = {
      finishTrial: (data) => { row = data; },
      pluginAPI: {
        setTimeout: (callback, ms) => {
          timers.push({ at: clock + (ms ?? 0), order: order++, callback });
        },
        clearAllTimeouts: () => { timers = []; },
      },
    };
    new Plugin(jsPsych).trial(inert(), trial);
    while (row === null && timers.length) {
      timers.sort((a, b) => a.at - b.at || a.order - b.order);
      const next = timers.shift();
      clock = next.at;
      next.callback();
    }
    if (row === null) {
      throw new Error(`a ${trial.phase} trial waits for a response with no deadline`);
    }
    // As in jsPsych, the node's data parameter is added to the row the plugin saves.
    const data = node.data && typeof node.data === 'object' ? node.data : {};
    return { ...row, ...data };
  });
  return { rows, drawsBeforeOffset };
}

// --- Command line ------------------------------------------------------------------------------

function parseArgs(argv) {
  const options = { assignmentId: null, streamOffset: 0, codeDir: HERE };
  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i + 1];
    if (argv[i] === '--assignment-id') options.assignmentId = Number(value);
    else if (argv[i] === '--stream-offset') options.streamOffset = Number(value);
    else if (argv[i] === '--code') options.codeDir = value;
    else throw new Error(`unknown argument ${argv[i]}`);
    if (value === undefined || value === '' || value.startsWith('--')) {
      throw new Error(`${argv[i]} takes a value`);
    }
    i += 1;
  }
  for (const key of ['assignmentId', 'streamOffset']) {
    if (!Number.isInteger(options[key]) || options[key] < 0) {
      throw new Error('--assignment-id and --stream-offset take non-negative integers');
    }
  }
  return options;
}

// Run when invoked as a script, also through a symbolic link.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { rows, drawsBeforeOffset } = await replay(parseArgs(process.argv.slice(2)));
    writeSync(2, `seeded draws before the stream offset: ${drawsBeforeOffset}\n`);
    const text = rows.map((row) => JSON.stringify(row)).join('\n') + '\n';
    process.stdout.write(text, () => process.exit(0));
  } catch (error) {
    writeSync(2, `replay: ${error.message}\n`);
    process.exit(1);
  }
}
