/**
 * The settings of Experiment 1 as participants ran it. Durations are given in frames at 60 Hz
 * (framesToMs) or in milliseconds. The session record saves this object as `config`.
 *
 * @module config
 */

export const CONFIG = {

  // -- Items --
  numItems: 7,                    // Items in the trained, novel and practice orderings
  numDistractorsPerTrial: 2,      // Distractors in a learning, IWL or arbitrage chain (always 2)
  distractorsPerRankBucket: 2,    // Learning distractors per rank bucket (one bucket per gap)
  numICLEndDistractors: 2,        // End distractors of each novel ordering
  numPracticeEndDistractors: 2,   // End distractors of the practice chain
  numQueryOnlyPracticeItems: 3,   // Items of the query-only practice block
  numICLOrderings: 5,             // Novel orderings of the ICL test (no shared items)

  // Probabilities of 0, 1 or 2 distractors between the queried items (learning).
  distractorsBetweenDist: { 0: 0.1, 1: 0.45, 2: 0.45 },

  // -- Trials --
  numQueryOnlyPracticeTrials: 10,        // Block 1 practice (adjacent pairs, no pair row)
  numQueryOnlyPracticeRetryTrials: 5,    // Each retry block of block 1
  numSinglehopPracticeTrials: 5,         // Block 2 practice (adjacent pairs)
  numMultiHopPracticeTrials: 5,          // Block 3 practice (symbolic distance 2 or 3)
  numExtraPracticeTrials: 5,             // Each retry block of blocks 2 and 3
  numTrainingTrials: 100,
  numTestTrialsPerType: 40,

  // -- Timing --
  timing: {
    fixationFrames: 30,                  // 500 ms
    feedbackCorrectFrames: 30,           // 500 ms before Space continues after a correct answer
    feedbackIncorrectFrames: 300,        // 5000 ms after an error or a timeout
    feedbackNeutralFrames: 60,           // 1000 ms on test trials
    feedbackContinueDeadlineMs: 10000,   // The trial ends by itself this long after Space works
    refreshRate: 60,
  },

  // -- Responses --
  responseKeys: { left: 'f', right: 'j' },
  responseDeadlineMs: 60000,      // Practice and learning
  testResponseDeadlineMs: 60000,  // Tests

  // -- Sequence constraints --
  maxCorrectSideStreak: 5,        // Longest run of the correct side, in the order trials are drawn
  maxDistractorsBetweenStreaks: { 0: 3, 1: 3, 2: 3 },  // Longest run per count (learning)
  maxQueryPairStreak: 2,          // Longest run of one queried pair (practice, learning)

  // -- Breaks --
  trainingBreakFrequency: 20,     // A break after every 20 learning trials
  testBreakFrequency: 20,         // A break after every 20 trials within a test (and between tests)

  // -- Practice --
  practiceAccuracyThreshold: 0.7, // Accuracy on the block just completed below which a retry runs
  practiceMaxRetries: 2,          // Retry blocks at most; then the session moves on

  // -- Context window --
  // Learning trials and the first single-step and multistep practice blocks show the chain
  // through a window of L pairs, L ~ Uniform(minContextPairs, all pairs), that keeps every link
  // between the queried items (utils.applyContextWindow). Practice retry blocks, tests and
  // masked trials show the whole chain.
  minContextPairs: 5,

  // -- Instructions --
  instructionMinViewMs: 5000,     // Each instruction page, on its first visit

  // -- Comprehension checks --
  comprehensionMaxRetries: 1,     // Each check: one retry, then a failure ends the session

  // -- Masked learning trials --
  iwlDisplayProportionTraining: 0.1,  // Share of learning trials with the context masked

  // -- Display --
  // Sizes in pixels at the smallest supported window (1024 x 700), where the display is 96vw =
  // 983 px wide; display.js scales them with the display. The query and the pairs use the same
  // image size.
  display: {
    imageSizePx: 84,                 // Every stimulus image
    pairConnectorHeightPx: 56,       // The arrow between the two images of a pair
    pairArrowImageGapPx: 12,         // Gap between the arrow and each image
    pairArrowHeadHeightPx: 18,       // Arrowhead height
    pairArrowCapWidthPx: 16,         // Arrow box width (the arrowhead's base)
    pairArrowShaftWidthPx: 5,        // Arrow shaft width
    pairRowGapPx: 26,                // Gap between neighboring pairs
    pairToQueryGapPx: 36,            // Gap between the query and the pair row (trials)
    instructionPairToQueryGapPx: 16, // The same gap on instruction pages
    queryImageGapPx: 22,             // Gap between each query image and the "?"
    responseSlotHeightPx: 84,        // Height of the slot of the key hints and the feedback
    maxWidthVw: 96,                  // Display width on trials: min(96vw, 1500px)
    maxWidthPx: 1500,
    instructionMaxWidthVw: 80,       // Display width on instruction pages:
    instructionMaxWidthPx: 1100,     //   min(80vw, 1100px, 125vh)
    instructionMaxWidthVh: 125,
    grayBoxFill: '#c8c4bc',          // Masked pair images
    grayBoxBorderPx: 2,
  },

  // -- Browser --
  // Smallest window; phones and tablets are refused.
  browser: {
    minWidth: 1024,
    minHeight: 700,
  },
};

/** Number of rank buckets: one above the first item, one per gap, one below the last. */
CONFIG.numRankBuckets = CONFIG.numItems + 1;

/**
 * Frames at the configured refresh rate, in milliseconds.
 * @param {number} frames
 * @returns {number}
 */
export function framesToMs(frames) {
  return Math.round((frames / CONFIG.timing.refreshRate) * 1000);
}
