# Accuracy and response-time models of Experiment 2, retained participants and all finishers:
# fixed effects into results/experiment2/models.csv, random effects into
# results/experiment2/random_effects.csv.
# Run from the repository root: Rscript analysis/experiment2/models.R
source(file.path("analysis", "experiment2", "common.R"))

FIXED <- "condition * log_distance + trial"
RUNG <- 3    # reported for both models and both sets: (1 + log_distance | participant)

rows <- list()
random_rows <- list()
for (set in SETS) {
  d <- main_questions(set)
  fits <- list(
    # Accuracy: every main question, timeouts counted as incorrect (glmer, binomial logit).
    accuracy = fit_ladder(ladder("is_correct", FIXED), d, "binomial", RUNG),
    # Response time: log RT of correct answers after outlier removal (|z| > 3; lmer, REML).
    rt = fit_ladder(ladder("log_rt", FIXED), rt_frame(d), "gaussian", RUNG))
  for (name in names(fits)) {
    estimates <- fit_estimates(fits[[name]], "condition", CONDITION_CODES)
    rows[[length(rows) + 1]] <- result_rows(name, set, estimates, fits[[name]])
    random_rows[[length(random_rows) + 1]] <- random_effect_rows(name, set, fits[[name]]$model)
  }
}
write_results(rows, c("accuracy", "rt"))
write_random_effects(random_rows)
