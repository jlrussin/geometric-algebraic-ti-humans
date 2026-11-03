/**
 * Every word a participant reads. This file is the source of truth for the participant-facing
 * text, exactly as participants saw it.
 *
 * - Every export is a pure function of the configuration (CONFIG), plus, where noted, the item
 *   tables (data/item_tables.json: item names, articles and relation words) or a few display
 *   strings. No DOM, no jsPsych, no I/O: the module can be imported in Node and in the browser.
 * - Numbers that are configuration values are filled in from the configuration (statements per
 *   question, seconds, window size). No progress counts are shown anywhere.
 * - Domain words are never typed: the instruction example uses `cfg.domains.instructions`, the
 *   question screens the domain whose table entry the caller passes, and every relation word
 *   ("is heavier than") and item name comes from the tables.
 * - Every returned string is HTML, and inserted values (item labels) are escaped, so the strings
 *   are safe to insert with innerHTML; except `instructionExample`, whose labels and statements
 *   are plain text (js/instructions.js escapes them), and the questionnaire, whose words are
 *   converted to plain text for SurveyJS (js/questionnaire.js).
 *
 * Participant-facing words: a trial is a "question", its lines are "statements", the line at the
 * top is "the question", the two options are "answers".
 */

// ---------------------------------------------------------------------------
// Helpers (not exported)
// ---------------------------------------------------------------------------

function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Bold an important phrase (Inter 600) so that a participant who skims still gets the idea. */
function b(html) {
  return `<strong>${html}</strong>`;
}

/** Values filled in from the configuration. */
function counts(cfg) {
  return {
    statementsPerQuestion: cfg.slotCount - 1,
    deadlineSeconds: Math.round(cfg.responseDeadlineMs / 1000),
  };
}

/** The domain's emphasis word inside a query phrase, in bold. */
function emphasize(phrase, emphasis) {
  const i = phrase.lastIndexOf(emphasis);
  if (i < 0) {
    throw new Error(`copy.question: emphasis "${emphasis}" is not part of "${phrase}"`);
  }
  return `${esc(phrase.slice(0, i))}<span class="relation">${esc(emphasis)}</span>`
    + esc(phrase.slice(i + emphasis.length));
}

const PRESS_SPACE_CONTINUE = 'Press space to continue.';
const PRESS_SPACE_START = 'Press space to start.';

/**
 * A no-break space. It binds the last two words of a paragraph whose wrap would otherwise leave
 * one word alone on its last line.
 */
const NBSP = '&nbsp;';
const RETURN_ON_PROLIFIC = 'Please return this study on Prolific.';

/** The bonus: on the instruction page I6b, and as a reminder on the main intro and the breaks. */
const BONUS_INSTRUCTIONS = `You earn a ${b('bonus')} for answering ${b('accurately')}, `
  + `and you receive an additional bonus for responding ${b('quickly')}.`;
const BONUS_REMINDER = `Remember: accuracy and speed determine your ${b('bonus payment')}.`;

// ---------------------------------------------------------------------------
// Item-table helpers (not exported)
// ---------------------------------------------------------------------------

/** The tables' entry for a domain (relation words and slot tables). */
function domainDef(tables, domainId) {
  const dom = tables && Array.isArray(tables.domains) && tables.domains.find((d) => d.domain_id === domainId);
  if (!dom) throw new Error(`copy.js: domain "${domainId}" is not in the item tables`);
  return dom;
}

/** Look up items of a domain's slotCount table by item_id; throws on an unknown id. */
function itemFinder(cfg, dom) {
  const slots = (dom.slot_tables || {})[String(cfg.slotCount)] || [];
  const byId = new Map();
  for (const s of slots) for (const it of s.items || []) byId.set(it.item_id, it);
  return (id) => {
    const it = byId.get(id);
    if (!it) throw new Error(`copy.js: item "${id}" is not in the ${dom.domain_id} ${cfg.slotCount}-slot table`);
    return it;
  };
}

/** Plain-text label with its article, as in the questions: "the pocket watch". */
function itemLabel(item) {
  return item.article ? `${item.article} ${item.name}` : item.name;
}

function capitalizeFirst(s) {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

/**
 * One statement, plain text: "{Subject} {relation_phrase} {object}." with the subject
 * capitalized. The same rule as trial-logic's `renderStatement` (not imported: trial-logic
 * imports this module).
 */
function statementText(subjectLabel, relationPhrase, objectLabel) {
  return `${capitalizeFirst(subjectLabel)} ${relationPhrase} ${objectLabel}.`;
}

/**
 * `cfg.instructionExample`, resolved against the instructions domain's table (validateConfig
 * rule 8 has checked it):
 *   items[c - 1] = the item at context position c (1-based, c = 1..N);
 *   screenStatements = the N - 1 statement numbers c in screen order, where statement c reads
 *   "item c + 1 {relation} item c" (the configuration's `lineOrder` lists 0-based statement
 *   indices, index i = statement i + 1);
 *   oneStep = [p, p + 1], context positions.
 */
function resolveExample(cfg, tables) {
  const spec = cfg.instructionExample;
  const dom = domainDef(tables, cfg.domains.instructions);
  const find = itemFinder(cfg, dom);
  return {
    dom,
    items: spec.itemIds.map(find),
    screenStatements: spec.lineOrder.map((i) => i + 1),
    oneStep: spec.oneStepQuery.slice(),
  };
}

// ---------------------------------------------------------------------------
// Shared prompts
// ---------------------------------------------------------------------------

/** "Press space to continue." (line 2 of the question screen's message). */
export function continuePrompt(cfg) {
  return PRESS_SPACE_CONTINUE;
}

// ---------------------------------------------------------------------------
// Screens, in session order
// ---------------------------------------------------------------------------

/** Loading. */
export function loading(cfg) {
  return 'Loading, please wait…';
}

/**
 * Browser check (shown only when it fails). `resize` and `resizeButton`: while the window is
 * smaller than the minimum; `windowTooSmall`: after the participant gives up; `mobile`: on a
 * phone or tablet.
 */
export function browserCheck(cfg) {
  const { minWidth, minHeight } = cfg.browser;
  return {
    windowTooSmall: 'This study needs a desktop or laptop computer with a window at least '
      + `${minWidth} × ${minHeight} pixels. ${RETURN_ON_PROLIFIC}`,
    mobile: `This study needs a desktop or laptop computer. ${RETURN_ON_PROLIFIC}`,
    // Shown while the window is too small (the participant can still enlarge it); the button
    // gives up and shows `windowTooSmall`.
    resize: `Please make this window larger, at least ${minWidth} × ${minHeight} pixels.`,
    resizeButton: "I can't make the window larger",
  };
}

/** Consent: the consent form approved for the study. The only screen that may scroll. */
export function consent(cfg) {
  const html = `
<div class="consent-head">
  <p class="consent-title">BROWN UNIVERSITY<br>CONSENT FOR RESEARCH PARTICIPATION</p>
  <p>Learning and Decision Making – Online (Prolific)<br>Version 4, April 8th, 2026</p>
</div>
<p>You are invited to take part in a Brown University research study. Your participation is voluntary.</p>
<ul class="consent-list">
  <li><p>RESEARCHER: Michael Frank PhD; (401) 863-6871.</p></li>
  <li><p>PURPOSE: The research study is about examining your performance on a series of computerized tasks as it relates to learning and decision making.</p>
    <p>In order to participate in this study, you must be healthy, between the ages of 18 and 65, and have no medical history of brain injury.</p></li>
  <li><p>PROCEDURES: You will be asked to complete a computerized task in which you will make decisions on various stimuli depending on the instructions and memory requirements for the task. You may also be asked to complete some brief questionnaires.</p></li>
  <li><p>You are allowed to skip any questions which you do not wish to answer.</p></li>
  <li><p>TIME INVOLVED: The study will take from approximately 10 minutes to 1 hour of your time. You will be notified of the duration of your participation prior to beginning.</p></li>
  <li><p>COMPENSATION: You will be paid a base rate that is the standard hourly minimum base pay of the current platform. In addition to this compensation, you may receive additional compensation (which may be in the form of monetary rewards or gift cards) based on your choices and/or performance on the available tasks. The amount of this bonus will scale directly with your performance on the task such that the amount of bonus received will be: correct performance on the task multiplied by 1/3 of minimum base rate of the online recruitment, and this will not exceed $5. If the task involves the opportunity to win this bonus, we will ensure that median base performance on this task is at least 50%, ensuring that half of participants earn at least 1/6 of the minimum base pay. In the event where the task is harder than expected for participants, we may choose to increase the scale on the equation above to ensure fair compensation. You will be notified prior to the study beginning of whether your study involves the opportunity to win this scalable bonus and be given the option not to participate. You will receive your compensation upon completing the task via your Prolific account in accordance with the payment policies of both Prolific and Brown University.</p></li>
  <li><p>RISKS: There are minimal risks with participation. There is a low probability of a breach of confidentiality. If this happened, it would be possible that other parties would know private information such as names and email addresses (please see “Confidentiality” section below).</p></li>
  <li><p>You are allowed to skip any questions you do not wish to answer in any questionnaire.</p></li>
  <li><p>BENEFITS: You may not directly benefit from being in this research study.</p></li>
  <li><p>CONFIDENTIALITY: Your records will be confidential. You will not be identified in any reports or publications resulting from the study. It is possible that representatives of the sponsor that supports the research study will want to come to Brown University to review your information.</p>
    <p>Representatives of regulatory agencies (including the Brown University Human Research Protection Program) may access your records. You may be asked for your Prolific.com username and email address for the purpose of the compensation through Prolific members services, however, research personnel will not have access to your bank information at any time. All experiments conducted online are hosted on a Brown University secure server. Your data, including responses to questionnaires, will be maintained on a password-protected database on that server. Your email address will be maintained in a location that is separate from the rest of your information. To preserve confidentiality, you will be assigned a number and you will automatically be identified on all forms by number only such that your name and data collected about you are not linked in any way. Furthermore, any data stored on a computer will reference you only by this number. Only investigators delegated to this study will have access to this data and none of this data will be shared with third parties. In general, neither we nor anyone can absolutely guarantee the security of data transmitted over the web.</p>
    <p>This research is covered by a Certificate of Confidentiality from the National Institutes of Health. The researchers with this Certificate may not disclose or use information, documents, or biospecimens that may identify you in any federal, state, or local civil, criminal, administrative, legislative, or other action, suit, or proceeding, or be used as evidence, for example, if there is a court subpoena, unless you have consented for this use. Information, documents, or biospecimens protected by this Certificate cannot be disclosed to anyone else who is not connected with the research except, if there is a federal, state, or local law that requires disclosure (such as to report child abuse or communicable diseases but not for federal, state, or local civil, criminal, administrative, legislative, or other proceedings, see below); if you have consented to the disclosure, including for your medical treatment; or if it is used for other scientific research, as allowed by federal regulations protecting research subjects. Brown University staff sometimes review studies like this one to make sure they are being done safely and correctly. If a review of this study takes place, your records may be examined. The reviewers will protect your confidentiality.</p></li>
  <li><p>VOLUNTARY: You do not have to be in this study if you do not want to be. Even if you decide to be in this study, you can change your mind and stop at any time.</p></li>
  <li><p>CONTACT INFORMATION: If you have any questions about your participation in this study, you can call the Principal Investigator, Michael Frank PhD at (401) 863-6871.</p></li>
  <li><p>YOUR RIGHTS: If you have questions about your rights as a research participant, you can contact Brown University’s Human Research Protection Program at 401-863-3050 or email them at <a href="mailto:IRB@Brown.edu">IRB@Brown.edu</a>.</p></li>
  <li><p>CONSENT TO PARTICIPATE: Clicking the button below confirms that you have read and understood the information in this document, are 18–65, and that you agree to volunteer as a research participant for this study.</p></li>
</ul>
<p>You can print a copy of this form.</p>`.trim();
  return { html, agreeButton: 'I agree', declineButton: 'I do not agree' };
}


/** Consent declined. Nothing is saved. */
export function consentDeclined(cfg) {
  return `You chose not to take part. ${RETURN_ON_PROLIFIC} You can close this window now.`;
}

/** Full screen: a "Welcome!" title and the warning in bold. */
export function fullscreen(cfg) {
  return {
    title: 'Welcome!',
    text: 'The study will now switch to full screen. '
      + b("Please stay in full screen until you finish, and please don't refresh or close this page."),
    button: 'Enter full screen',
  };
}

/**
 * Instructions: four pages, each built up one step at a time, every step its own screen with
 * its own id: I1 "Before you start"; I2a-c, the statements, the rule ("answer according to the
 * given statements") and the keys, above an example question; I6a-c, one paragraph per step:
 * the time limit (the deadline from `responseDeadlineMs`), the bonus and what follows an answer;
 * I8 "Ready to start?", which says that the instructions cannot be reviewed once the task
 * begins. Only the first page and the last have a title.
 * Every step of a page carries all of the page's steps as `steps` and shows the first
 * `shownSteps` of them; the rest are laid out but hidden, so the paragraphs already shown and
 * the example below never move. `example` is true on the steps that show the example question
 * (`instructionExample`) below the text.
 * @param {object} cfg
 * @param {object} tables - The item tables (data/item_tables.json).
 * @returns {{pages: Array<{id: string, title: ?string, steps: string[], shownSteps: number,
 *   example: boolean}>, backButton: string, nextButton: string}}
 */
export function instructions(cfg, tables) {
  const n = counts(cfg);
  const groups = [
    {
      id: 'I1',
      title: 'Before you start',
      steps: [
        `In this study you will answer questions using short lists of ${b('statements')}. `
        + `Please read each page of these instructions ${b('carefully')}.`,
      ],
    },
    {
      id: 'I2',
      title: null,
      steps: [
        `Each question will appear with a list of ${b(`${n.statementsPerQuestion} statements`)}.`,
        `Your goal is to answer ${b('according to the given statements')}.`,
        `Press ${b('F')} for the ${b('left')} answer, ${b('J')} for the ${b('right')}.`,
      ],
      example: true,
    },
    {
      id: 'I6',
      title: null,
      steps: [
        `You have up to ${b(`${n.deadlineSeconds} seconds`)} for each question. `
        + `Answer as ${b('quickly and accurately')} as you can.`,
        BONUS_INSTRUCTIONS,
        `After each answer you will see which you chose, but ${b('not whether it was correct')}.`,
      ],
    },
    {
      id: 'I8',
      title: 'Ready to start?',
      steps: [
        `Feel free to use the ${b('Back')} button to review the previous instructions now. `
        + `Once the task begins, ${b("you won't be able to go back")}.`,
      ],
    },
  ];

  const pages = [];
  for (const g of groups) {
    g.steps.forEach((_, i) => {
      pages.push({
        id: g.steps.length > 1 ? `${g.id}${'abcdefgh'[i]}` : g.id,
        title: g.title,
        steps: g.steps,
        shownSteps: i + 1,
        example: Boolean(g.example),
      });
    });
  }
  return { pages, backButton: 'Back', nextButton: 'Next' };
}

/**
 * The instruction pages' example question: a static question screen built from
 * `cfg.instructionExample` (objects of the instructions domain, relation from the tables). It
 * shows the N - 1 statements in the example's screen order and asks about the one-step pair
 * [p, p + 1], with the statements' answer (p + 1) on the left (F).
 * @param {object} cfg
 * @param {object} tables
 * @returns {{questionHtml: string, leftLabel: string, rightLabel: string, statements: string[]}}
 */
export function instructionExample(cfg, tables) {
  const ex = resolveExample(cfg, tables);
  const label = (c) => itemLabel(ex.items[c - 1]);
  const statement = (c) => statementText(label(c + 1), ex.dom.relation_phrase, label(c));
  const [right, left] = ex.oneStep;
  return {
    questionHtml: question(cfg, ex.dom),
    leftLabel: label(left),
    rightLabel: label(right),
    statements: ex.screenStatements.map(statement),
  };
}

/** Build error (the session could not be set up). */
export function buildError(cfg) {
  return `Something went wrong while setting up the study. ${RETURN_ON_PROLIFIC} Sorry for the trouble.`;
}

/**
 * Main intro, right after the instructions: the start, the bonus reminder of the breaks and the
 * breaks, one paragraph each. Shown for at least `mainIntroMinViewMs`.
 * @param {object} cfg
 * @returns {{title: null, paragraphs: string[], prompt: string}}
 */
export function mainIntro(cfg) {
  return {
    title: null,
    paragraphs: [
      'The main task starts now.',
      BONUS_REMINDER,
      'There will be short breaks along the way.',
    ],
    prompt: PRESS_SPACE_START,
  };
}

/**
 * Break: the screen draws a progress bar (no counts), then `paragraphs`, then the bonus
 * `reminder`, then the prompt.
 */
export function breakScreen(cfg) {
  return {
    paragraphs: ['Take a short break if you need one.'],
    reminder: BONUS_REMINDER,
    prompt: PRESS_SPACE_CONTINUE,
  };
}

/** Questionnaire intro (right after the main questions). */
export function questionnaireIntro(cfg) {
  return {
    paragraphs: [
      'A few questions about how you found your answers and about the study. '
      + `There are no right or wrong answers. You can skip any${NBSP}question.`,
    ],
    prompt: PRESS_SPACE_CONTINUE,
  };
}

/**
 * Questionnaire: one question per page, all optional, the same for every participant, in this
 * order: the strategy questions (the free-text `sp_strategy` before anything that could prime
 * it), the manipulation check `qn_statements_true`, then the questions about the study.
 * Types: `text` = a text box; `choice` = one choice from `choices`; `rating` = `rateCount`
 * buttons with labels at the two ends. `detailPrompt` opens a text box when the answer equals
 * `detailIf` (saved as `<id>_details`).
 */
export function questionnaire(cfg) {
  const questions = [
    {
      id: 'sp_strategy',
      type: 'text',
      prompt: 'In a few sentences, how did you find your answers?',
    },
    {
      id: 'qn_statements_true',
      type: 'choice',
      prompt: 'In the main questions, how many of the statements were true of the real world?',
      choices: ['All of them', 'Most of them', 'About half of them', 'Few of them', 'None of them', "I don't know"],
    },
    {
      id: 'sp_knowledge_rating',
      type: 'choice',
      prompt: 'How often did you answer from what you know about the real world instead of from the statements?',
      choices: ['Never', 'Rarely', 'Sometimes', 'Often', 'Always'],
    },
    {
      id: 'sp_notes',
      type: 'choice',
      prompt: 'Did you write anything down while answering?',
      choices: ['Yes', 'No'],
    },
    {
      id: 'qn_difficulty',
      type: 'rating',
      prompt: 'Overall, how difficult were the main questions?',
      rateCount: 5,
      minLabel: 'Very easy',
      maxLabel: 'Very hard',
    },
    {
      id: 'qn_technical',
      type: 'choice',
      prompt: 'Did you have any technical problems, such as the page freezing or keys not responding?',
      choices: ['No', 'Yes'],
      detailIf: 'Yes',
      detailPrompt: 'Please describe.',
    },
    {
      id: 'qn_other_problems',
      type: 'choice',
      prompt: 'Did anything else go wrong, or was anything unclear?',
      choices: ['No', 'Yes'],
      detailIf: 'Yes',
      detailPrompt: 'Please describe.',
    },
    {
      id: 'qn_comments',
      type: 'text',
      prompt: 'Is there anything else you want to tell us?',
    },
  ];
  return { questions, nextButton: 'Next' };
}

/** Saving. */
export function saveData(cfg) {
  return "Saving your answers… Please don't close this page.";
}

/**
 * Debrief: a title, a section heading (`heading`, drawn smaller than the title) and one
 * paragraph, the same in both conditions.
 */
export function debrief(cfg) {
  return {
    title: 'Thank you for your participation.',
    heading: 'Study details',
    paragraphs: [
      'Some statements in this study may have been false. This was on purpose. The study was designed to '
      + 'investigate how people reason when statements conflict with what they know.',
    ],
    prompt: PRESS_SPACE_CONTINUE,
  };
}

// ---------------------------------------------------------------------------
// Question screen strings
// ---------------------------------------------------------------------------

/**
 * The question at the top (`question_html`). `phrase` is the domain's table entry (fields
 * `query_phrase` and `query_emphasis`); the emphasis word is wrapped in <span class="relation">.
 */
export function question(cfg, phrase) {
  return `According to the statements, which ${emphasize(phrase.query_phrase, phrase.query_emphasis)}?`;
}

/** Message line 1 after an answer: "You chose the cat." */
export function confirmation(cfg, chosenLabel) {
  return `You chose ${esc(chosenLabel)}.`;
}

/** Message line 1 when time runs out. */
export function timeoutMessage(cfg) {
  return b('Time is up for this question.');
}
