/**
 * The consent form and the closing screens, as participants saw them.
 *
 * @module consent
 */

export const CONSENT_HTML = `
<div class="consent-form">
  <h1>BROWN UNIVERSITY CONSENT FOR RESEARCH PARTICIPATION</h1>
  <p><strong>Learning and Decision Making – Online (Prolific)</strong><br>
  Version 4, April 8th, 2026</p>

  <p>You are invited to take part in a Brown University research study. Your participation is voluntary.</p>

  <h2>Researcher</h2>
  <p>Michael Frank PhD; (401) 863-6871</p>

  <h2>Purpose</h2>
  <p>The research study is about examining your performance on a series of computerized tasks as it relates to learning and decision making. In order to participate in this study, you must be healthy, between the ages of 18 and 65, and have no medical history of brain injury.</p>

  <h2>Time Involved</h2>
  <p>The study will take from approximately 10 minutes to 1 hour of your time. You will be notified of the duration of your participation prior to beginning.</p>

  <h2>Compensation</h2>
  <p>You will be paid a base rate that is the standard hourly minimum base pay of the current platform. In addition to this compensation, you may receive additional compensation (which may be in the form of monetary rewards or gift cards) based on your choices and/or performance on the available tasks. The amount of this bonus will scale directly with your performance on the task such that the amount of bonus received will be: correct performance on the task multiplied by 1/3 of minimum base rate of the online recruitment, and this will not exceed $5. If the task involves the opportunity to win this bonus, we will ensure that median base performance on this task is at least 50%, ensuring that half of participants earn at least 1/6 of the minimum base pay. In the event where the task is harder than expected for participants, we may choose to increase the scale on the equation above to ensure fair compensation. You will be notified prior to the study beginning of whether your study involves the opportunity to win this scalable bonus and be given the option not to participate.</p>
  <p>You will receive your compensation upon completing the task via your Prolific account in accordance with the payment policies of both Prolific and Brown University.</p>

  <h2>Risks</h2>
  <p>There are minimal risks with participation. There is a low probability of a breach of confidentiality. If this happened, it would be possible that other parties would know private information such as names and email addresses (please see "Confidentiality" section below).</p>
  <p>You are allowed to skip any questions you do not wish to answer in any questionnaire.</p>

  <h2>Benefits</h2>
  <p>You may not directly benefit from being in this research study.</p>

  <h2>Confidentiality</h2>
  <p>Your records will be confidential. You will not be identified in any reports or publications resulting from the study. It is possible that representatives of the sponsor that supports the research study will want to come to Brown University to review your information. Representatives of regulatory agencies (including the Brown University Human Research Protection Program) may access your records. You may be asked for your Prolific.com username and email address for the purpose of the compensation through Prolific members services, however, research personnel will not have access to your bank information at any time. All experiments conducted online are hosted on a Brown University secure server. Your data, including responses to questionnaires, will be maintained on a password-protected database on that server. Your email address will be maintained in a location that is separate from the rest of your information. To preserve confidentiality, you will be assigned a number and you will automatically be identified on all forms by number only such that your name and data collected about you are not linked in any way. Furthermore, any data stored on a computer will reference you only by this number. Only investigators delegated to this study will have access to this data and none of this data will be shared with third parties. In general, neither we nor anyone can absolutely guarantee the security of data transmitted over the web.</p>
  <p>This research is covered by a Certificate of Confidentiality from the National Institutes of Health. The researchers with this Certificate may not disclose or use information, documents, or biospecimens that may identify you in any federal, state, or local civil, criminal, administrative, legislative, or other action, suit, or proceeding, or be used as evidence, for example, if there is a court subpoena, unless you have consented for this use. Information, documents, or biospecimens protected by this Certificate cannot be disclosed to anyone else who is not connected with the research except, if there is a federal, state, or local law that requires disclosure (such as to report child abuse or communicable diseases but not for federal, state, or local civil, criminal, administrative, legislative, or other proceedings, see below); if you have consented to the disclosure, including for your medical treatment; or if it is used for other scientific research, as allowed by federal regulations protecting research subjects. Brown University staff sometimes review studies like this one to make sure they are being done safely and correctly. If a review of this study takes place, your records may be examined. The reviewers will protect your confidentiality.</p>

  <h2>Voluntary</h2>
  <p>You do not have to be in this study if you do not want to be. Even if you decide to be in this study, you can change your mind and stop at any time.</p>

  <h2>Contact Information</h2>
  <p>If you have any questions about your participation in this study, you can call the Principal Investigator, Michael Frank PhD at (401) 863-6871.</p>

  <h2>Your Rights</h2>
  <p>If you have questions about your rights as a research participant, you can contact Brown University's Human Research Protection Program at 401-863-3050 or email them at IRB@Brown.edu.</p>

  <h2>Consent to Participate</h2>
  <p>Clicking the button below confirms that you have read and understood the information in this document, are 18–65, and that you agree to volunteer as a research participant for this study. You can print a copy of this form.</p>

  <hr>
  <p><strong>Press <kbd>Y</kbd> to consent and continue, or close this window to decline.</strong></p>
</div>
`;

/** Shown after the session's data are saved, at the end of a completed session. */
export const THANK_YOU_HTML = `
    <div class="debrief-screen">
      <h2>Thank you for completing this experiment!</h2>
      <p>We appreciate your participation. Your responses have been recorded.</p>
      <p>Press <kbd>Space</kbd> to finish.</p>
    </div>
  `;

/** Shown when a comprehension check was failed on both attempts; the session ends here. */
export const COMPREHENSION_FAILED_HTML = `
  <div class="comprehension-failed-screen">
    <h2>We're unable to continue with this session.</h2>
    <p>Thank you for your time. You may now close this window.</p>
  </div>
`;
