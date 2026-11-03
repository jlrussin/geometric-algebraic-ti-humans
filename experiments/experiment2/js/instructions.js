/**
 * The instruction screens.
 *
 * All words come from js/copy.js (`instructions(cfg, tables)`), which also defines the pages:
 * I1, I2a-c, I6a-c and I8. Each step of a page is its own screen and adds one paragraph. Each
 * screen is a fixed 1024 × 700 frame with the title top-left of the 640-px column;
 * js/experiment.js shows them with jsPsych's instructions plugin and moves its Back and Next
 * buttons into the frame's bottom bar (y 636-676).
 *
 * Nothing moves between the steps of a page: every step lays out all of the page's paragraphs
 * and hides those of the steps not yet shown (`visibility`, like every other state change), so
 * the paragraphs already shown and the example below stay exactly in place.
 *
 * I2 shows an example question at a reduced scale (`--example-scale`), at the same place on
 * every step (`--example-top`), built by copy.js `instructionExample` and drawn with the question
 * screen's markup and classes (the regions of js/question-trial-plugin.js except the message
 * line, all visible, nothing chosen). The example is static, not answerable.
 *
 * @module instructions
 */

import { instructions, instructionExample } from './copy.js';

function escapeText(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * The example question: a static question stage, as js/question-trial-plugin.js draws it while
 * waiting for an answer (nothing chosen), without the message line, which a static example
 * never fills (styles/experiment.css, `.example-frame`).
 * @param {object} cfg - CONFIG.
 * @param {object} tables - The item tables.
 * @returns {string}
 */
function exampleStageHtml(cfg, tables) {
  const ex = instructionExample(cfg, tables);
  const d = cfg.display;
  const width = d.statementsColumnWidthPx;
  const statements = ex.statements
    .map((t) => `<div class="q-statement" style="height: calc(${d.statementPitchPx} * var(--u))">`
      + `<span class="example-statement-text">${escapeText(t)}</span></div>`)
    .join('');
  const answer = (side, label, key) => `<div class="q-answer is-${side}"><div class="q-answer-unit">`
    + `<span class="q-label">${escapeText(label)}</span><span class="keycap">${key}</span></div></div>`;
  return '<div class="example-frame" aria-hidden="true"><div class="q-stage chosen-outline">'
    + `<div class="q-question" style="font-size: calc(${d.queryFontPx} * var(--u))">${ex.questionHtml}</div>`
    + `<div class="q-answers">${answer('left', ex.leftLabel, 'F')}${answer('right', ex.rightLabel, 'J')}</div>`
    + `<div class="q-statements" style="width: calc(${width} * var(--u)); left: calc(50% - ${width / 2} * var(--u));`
    + ` font-size: calc(${d.statementFontPx} * var(--u)); line-height: calc(${d.statementPitchPx} * var(--u))">`
    + `${statements}</div>`
    + '</div></div>';
}

/**
 * The instruction screens, one per step, as HTML strings for jsPsych's instructions plugin.
 * @param {object} cfg - CONFIG.
 * @param {object} tables - The item tables.
 * @returns {{pages: string[], ids: string[], backButton: string, nextButton: string}}
 */
export function buildInstructionPages(cfg, tables) {
  const ins = instructions(cfg, tables);
  const pages = ins.pages.map((page) => {
    // Every paragraph of the page, those of the steps not yet reached hidden.
    const paragraphs = page.steps
      .map((text, i) => (i < page.shownSteps
        ? `<p class="ts-step">${text}</p>`
        : `<p class="ts-step is-hidden" aria-hidden="true">${text}</p>`))
      .join('');
    const example = page.example ? exampleStageHtml(cfg, tables) : '';
    // Untitled pages start their text where a title would be.
    const title = page.title ? `<h1 class="ts-title">${page.title}</h1>` : '';
    return `<div class="frame no-select"><div class="text-screen">${title}${paragraphs}${example}</div></div>`;
  });
  return {
    pages,
    ids: ins.pages.map((p) => p.id),
    backButton: ins.backButton,
    nextButton: ins.nextButton,
  };
}
