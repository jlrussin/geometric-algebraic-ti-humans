# Agree and conflict questions in the shuffled condition: models with question type in place of
# condition, and their checks (all finishers, waves, answer rule, participant-level tests).
# Run from the repository root: Rscript analysis/experiment2/agree_conflict.R
source(file.path("analysis", "experiment2", "common.R"))

FIXED <- "type * log_distance + trial"
WAVE_FIXED <- "type * log_distance * wave + trial"
TOP <- c("log_distance", "type")    # participant slopes of the two rungs above the five
RUNG <- 5    # reported for both models: (1 + log_distance | participant), rung 5 of 7
MIN_PER_TYPE <- 4    # participant-level response times: answers of each type a participant needs

model_rows <- function(name, set, fit, slopes = FALSE) {
  estimates <- if (slopes) fit_estimates(fit, "type", TYPE_CODES) else
    coefficient_rows(fit$model, fit$summary)
  result_rows(name, set, estimates, fit)
}

# Per participant, least squares of `dv ~ type * log_distance + trial` on their own answers
# (at least four, and min_per_type of each type); participants whose fit cannot estimate every
# coefficient are left out. Participants come in numeric assignment_id order, the order of the
# reported randomization p values.
participant_coefficients <- function(d, dv, min_per_type = 0) {
  f <- stats::as.formula(paste(dv, "~ type * log_distance + trial"))
  per <- lapply(split(d, d$participant, drop = TRUE), function(p) {
    p <- p[stats::complete.cases(p[all.vars(f)]), , drop = FALSE]
    if (nrow(p) < 4 || min(table(factor(p$type, TYPE_CODES))) < min_per_type) return(NULL)
    fit <- stats::lm(f, data = p)
    if (fit$rank < length(stats::coef(fit))) return(NULL)
    stats::coef(fit)[c("type", "type:log_distance")]
  })
  do.call(rbind, per)
}

# One-sample t and sign-flip randomization test of each coefficient across participants.
coefficient_tests <- function(coefs) {
  rbind(one_sample_row("type", coefs[, "type"]),
        one_sample_row("type:log_distance", coefs[, "type:log_distance"]))
}

retained <- main_questions("retained")
accuracy_data <- shuffled_only(retained)
rt_data <- shuffled_only(rt_frame(retained))
rt_answered_data <- shuffled_only(rt_frame(retained, answered = TRUE))
all_finishers <- main_questions("all_finishers")
rows <- list()

# The two models (retained participants), with the distance slope on each question type.
fit <- fit_ladder(ladder("is_correct", FIXED, TOP), accuracy_data, "binomial", RUNG)
rows[[length(rows) + 1]] <- model_rows("agree_conflict_accuracy", "retained", fit, slopes = TRUE)
fit <- fit_ladder(ladder("log_rt", FIXED, TOP), rt_data, "gaussian", RUNG)
rows[[length(rows) + 1]] <- model_rows("agree_conflict_rt", "retained", fit, slopes = TRUE)

# Checks refit in parallel from the reported rung, which each must pass; `set` is each check's
# participant set.
jobs <- list(
  # All finishers: the two models above.
  agree_conflict_accuracy = list(set = "all_finishers", dv = "is_correct", fixed = FIXED,
                                 data = shuffled_only(all_finishers), family = "binomial"),
  agree_conflict_rt = list(set = "all_finishers", dv = "log_rt", fixed = FIXED,
                           data = shuffled_only(rt_frame(all_finishers)), family = "gaussian"),
  # Waves: every term but `trial` crossed with `wave` (+0.5 wave 2, -0.5 wave 1), so each
  # coefficient without `wave` is the effect averaged over the two waves and its interaction with
  # `wave` the difference between them (wave 2 minus wave 1).
  agree_conflict_accuracy_waves = list(set = "retained", dv = "is_correct", fixed = WAVE_FIXED,
                                       data = accuracy_data, family = "binomial"),
  agree_conflict_rt_waves = list(set = "retained", dv = "log_rt", fixed = WAVE_FIXED,
                                 data = rt_data, family = "gaussian"),
  # The other answer rule: accuracy without timeouts; response times of all answered questions.
  agree_conflict_accuracy_timeouts_dropped = list(
    set = "retained", dv = "is_correct", fixed = FIXED,
    data = accuracy_data[!accuracy_data$is_timed_out, ], family = "binomial"),
  agree_conflict_rt_all_answered = list(set = "retained", dv = "log_rt", fixed = FIXED,
                                        data = rt_answered_data, family = "gaussian"))
fits <- refit_at_rung(jobs, RUNG, TOP)
for (name in names(jobs)) {
  rows[[length(rows) + 1]] <- model_rows(name, jobs[[name]]$set, fits[[name]])
}

# Participant-level tests of each participant's `type` and `type:log_distance` coefficients;
# prints how many of the shuffled participants each test leaves out.
participant_level <- list(
  agree_conflict_accuracy_participant_level = participant_coefficients(accuracy_data, "is_correct"),
  agree_conflict_rt_participant_level = participant_coefficients(rt_data, "log_rt", MIN_PER_TYPE),
  agree_conflict_rt_all_answered_participant_level =
    participant_coefficients(rt_answered_data, "log_rt", MIN_PER_TYPE))
n_shuffled <- length(unique(accuracy_data$participant))
for (name in names(participant_level)) {
  n_tested <- nrow(participant_level[[name]])
  cat(sprintf("%s: %d of %d participants, %d left out\n", name, n_tested, n_shuffled,
              n_shuffled - n_tested))
  rows[[length(rows) + 1]] <- result_rows(name, "retained",
                                          coefficient_tests(participant_level[[name]]))
}

write_results(rows, c(names(jobs), names(participant_level)))
