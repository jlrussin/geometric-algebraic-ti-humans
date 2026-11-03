/**
 * The questionnaire (the strategy questions and the questions about the study, the same for
 * every participant), with @jspsych/plugin-survey 4.0.0 (SurveyJS).
 *
 * One question per page; every question is optional. All words come from js/copy.js
 * (`questionnaire(cfg)`; its intro screen is `questionnaireIntro(cfg)`, a continue screen built
 * in js/experiment.js). Each page is its own jsPsych trial, so each saved row holds one question:
 * phase 'questionnaire', `question_id` (the copy id, e.g. `sp_strategy`), `question_number`
 * (1-based position in the list), and `response_json` (js/save.js `finalizeTrialRow` turns
 * SurveyJS's `response` object into JSON). A skipped question is absent from that object, so a
 * page left unanswered saves `{}`.
 *
 * The copy.js question types:
 *   text   → SurveyJS `comment` (a text box);
 *   choice → `radiogroup`;
 *   rating → `rating` buttons 1..rateCount with end labels;
 *   `detailPrompt` / `detailIf` → a second text box on the same page, shown only when the
 *            answer equals `detailIf`, saved as `<id>_details`.
 *
 * @module questionnaire
 */

import { CONFIG } from './config.js';
import { questionnaire } from './copy.js';

/**
 * Blur the active element so that a stale key (e.g. Space from the screen before) cannot press
 * the survey's auto-focused button.
 */
function blurActiveElement() {
  if (document.activeElement) document.activeElement.blur();
}

/** Plain text for SurveyJS titles and choices (copy.js strings are HTML-safe text). */
function plain(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.textContent;
}

/**
 * SurveyJS elements for one copy.js question.
 * @param {object} q - A copy.js questionnaire question.
 * @returns {object[]}
 */
function surveyElements(q) {
  const base = { name: q.id, title: plain(q.prompt), isRequired: false };
  if (q.type === 'text') {
    return [{ ...base, type: 'comment', rows: 5, autoGrow: false, allowResize: false }];
  }
  if (q.type === 'rating') {
    return [{
      ...base,
      type: 'rating',
      rateMin: 1,
      rateMax: q.rateCount,
      minRateDescription: plain(q.minLabel),
      maxRateDescription: plain(q.maxLabel),
      // Buttons always: 'auto' falls back to a dropdown on narrow widths.
      displayMode: 'buttons',
    }];
  }
  if (q.type === 'choice') {
    const elements = [{ ...base, type: 'radiogroup', choices: q.choices.map(plain) }];
    if (q.detailPrompt) {
      elements.push({
        type: 'comment',
        name: `${q.id}_details`,
        title: plain(q.detailPrompt),
        isRequired: false,
        rows: 3,
        autoGrow: false,
        allowResize: false,
        visibleIf: `{${q.id}} = ${JSON.stringify(plain(q.detailIf))}`,
      });
    }
    return elements;
  }
  throw new Error(`[questionnaire] unknown question type "${q.type}" for ${q.id}`);
}

/**
 * The questionnaire pages, one survey trial per question (after the
 * questionnaire intro).
 * @returns {object[]}
 */
export function buildQuestionnaireTrials() {
  const source = questionnaire(CONFIG);
  return source.questions.map((q, index) => ({
    type: jsPsychSurvey,
    survey_json: {
      showQuestionNumbers: 'off',
      questionErrorLocation: 'bottom',
      completeText: plain(source.nextButton),
      showCompletedPage: false,
      pages: [{ elements: surveyElements(q) }],
    },
    min_width: 'auto',
    data: { phase: 'questionnaire', question_id: q.id, question_number: index + 1 },
    on_load: blurActiveElement,
  }));
}
