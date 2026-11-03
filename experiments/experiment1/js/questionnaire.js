/**
 * The questionnaire after the tests, as participants saw it: ten questions, one per screen,
 * each headed "Question X of 10".
 *
 * @module questionnaire
 */

const QUESTIONS = [
  {
    id: 'q1_strategy',
    elements: [{
      type: 'comment',
      name: 'q1_strategy',
      title: 'In a few sentences, describe how you approached this task. What did you do to try to figure out which object the aliens preferred?',
      rows: 4,
      isRequired: true,
    }],
  },
  {
    id: 'q2_noticing',
    elements: [{
      type: 'comment',
      name: 'q2_noticing',
      title: 'Did you notice anything about the task that stood out to you, or anything that changed over the course of the experiment?',
      rows: 4,
      isRequired: true,
    }],
  },
  {
    id: 'q3_difficulty',
    elements: [{
      type: 'comment',
      name: 'q3_difficulty',
      title: 'Did you find any part of the experiment particularly easy or difficult? If so, which part and why?',
      rows: 4,
      isRequired: true,
    }],
  },
  {
    id: 'q4_display_comp',
    elements: [{
      type: 'rating',
      name: 'q4_display_comp',
      title: 'How easy or difficult was it to understand the display with the clues?',
      rateMin: 1,
      rateMax: 7,
      minRateDescription: 'Very difficult',
      maxRateDescription: 'Very easy',
      // Buttons, not the dropdown SurveyJS uses when it judges the page too narrow.
      displayMode: 'buttons',
      isRequired: true,
    }],
  },
  {
    id: 'q5_strategy_mc',
    elements: [{
      type: 'radiogroup',
      name: 'q5_strategy_mc',
      title: 'During the learning phase, did you try to memorize which objects the aliens preferred, read the clues on the display each time, or some combination?',
      choices: [
        'Mostly memorized',
        'Mostly read the display',
        'Used a mix of both',
      ],
      showOtherItem: true,
      otherText: 'Other (please describe)',
      isRequired: true,
    }],
  },
  {
    id: 'q6_strategy_change',
    elements: [{
      type: 'comment',
      name: 'q6_strategy_change',
      title: 'Did your strategy change over the course of the experiment? If so, how?',
      rows: 4,
      isRequired: true,
    }],
  },
  {
    id: 'q7_overall_diff',
    elements: [{
      type: 'rating',
      name: 'q7_overall_diff',
      title: 'Overall, how difficult was this experiment?',
      rateMin: 1,
      rateMax: 7,
      minRateDescription: 'Very easy',
      maxRateDescription: 'Very difficult',
      displayMode: 'buttons',
      isRequired: true,
    }],
  },
  {
    id: 'q8_hypothesis',
    elements: [{
      type: 'comment',
      name: 'q8_hypothesis',
      title: 'What do you think this experiment was trying to study?',
      rows: 4,
      isRequired: true,
    }],
  },
  {
    id: 'q9_technical',
    elements: [
      {
        type: 'radiogroup',
        name: 'q9_technical',
        title: 'Did you experience any technical problems during the experiment (e.g., images not loading, display glitches, keys not responding)?',
        choices: ['No', 'Yes'],
        isRequired: true,
      },
      {
        type: 'comment',
        name: 'q9_technical_details',
        title: 'Please describe:',
        rows: 3,
        visibleIf: '{q9_technical} = "Yes"',
      },
    ],
  },
  {
    id: 'q10_anything_else',
    elements: [{
      type: 'comment',
      name: 'q10_anything_else',
      title: 'Is there anything else you\'d like to tell us about your experience?',
      rows: 4,
      isRequired: false,
    }],
  },
];

/**
 * Remove the focus from the page, so that the Space that left the previous screen does not
 * press the survey's focused button.
 */
function blurActiveElement() {
  if (document.activeElement) document.activeElement.blur();
}

/**
 * The questionnaire's timeline nodes: an introduction, then one survey screen per question.
 * @returns {object[]}
 */
export function buildQuestionnaireTrials() {
  const totalQuestions = QUESTIONS.length;
  const trials = [];

  trials.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div style="max-width: 700px; margin: 0 auto; text-align: center;">
        <h2>Almost done!</h2>
        <p>Before we finish, we have a few questions about your experience.</p>
        <p>Press <kbd>Space</kbd> to continue.</p>
      </div>
    `,
    choices: [' '],
    data: { phase: 'questionnaire_intro' },
  });

  QUESTIONS.forEach((q, index) => {
    const isLast = index === totalQuestions - 1;

    // The progress header, an html element of the survey.
    const progressElement = {
      type: 'html',
      name: `progress_${index}`,
      html: `<div class="questionnaire-progress">Question ${index + 1} of ${totalQuestions}</div>`,
    };

    trials.push({
      type: jsPsychSurvey,
      survey_json: {
        showQuestionNumbers: false,
        completeText: isLast ? 'Submit' : 'Next',
        goNextPageAutomatic: false,
        allowCompleteSurveyAutomatic: false,
        pages: [{
          elements: [progressElement, ...q.elements],
        }],
      },
      data: {
        phase: 'questionnaire',
        question_id: q.id,
        question_number: index + 1,
      },
      on_load: blurActiveElement,
    });
  });

  return trials;
}
