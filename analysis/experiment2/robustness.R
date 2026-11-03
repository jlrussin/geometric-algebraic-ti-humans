# Robustness checks of the Experiment 2 accuracy and response-time models: waves, round 2, the
# other answer rule, participant-level tests, leaving one out, Lee bounds, distance codings.
# Run from the repository root: Rscript analysis/experiment2/robustness.R
source(file.path("analysis", "experiment2", "common.R"))

FIXED <- "condition * log_distance + trial"
WAVE_FIXED <- "condition * log_distance * wave + trial"
RUNG <- 3    # reported for both models: (1 + log_distance | participant)
RANDOM <- "(1 + log_distance | participant)"
TERMS <- c("condition", "log_distance", "condition:log_distance")    # leaving one out
N_BOOTSTRAP <- 2000    # Lee bounds: bootstrap samples, seeded with SEED

retained <- main_questions("retained")
outcomes <- list(
  accuracy = list(dv = "is_correct", family = "binomial", data = retained),
  rt = list(dv = "log_rt", family = "gaussian", data = rt_frame(retained)))
rows <- list()
add <- function(model, set, estimates, fit = NULL) {
  rows[[length(rows) + 1]] <<- result_rows(model, set, estimates, fit)
}


# Waves and the second round of the second wave
# Wave model: every term but `trial` crossed with `wave` (+0.5 wave 2, -0.5 wave 1), so each
# coefficient without `wave` is the effect averaged over the two waves and its interaction with
# `wave` the difference between them (wave 2 minus wave 1); slope_<condition>_by_wave likewise
# for the distance slope in a condition. The second round of the second wave recruited congruent
# participants only; the second refit leaves them out. Both refits start at the reported rung.

jobs <- list()
for (o in names(outcomes)) {
  x <- outcomes[[o]]
  jobs[[paste0(o, "_waves")]] <- c(x[c("dv", "family", "data")], fixed = WAVE_FIXED)
  without <- x$data[!(x$data$allocation_round %in% 2), , drop = FALSE]
  without$participant <- droplevels(without$participant)
  without$item_pair <- droplevels(without$item_pair)
  jobs[[paste0(o, "_without_round_2")]] <- list(dv = x$dv, family = x$family, data = without,
                                               fixed = FIXED)
}
fits <- refit_at_rung(jobs, RUNG)
for (name in names(jobs)) {
  if (endsWith(name, "_waves")) {
    m <- fits[[name]]$model
    estimates <- coefficient_rows(m, fits[[name]]$summary)
    for (suffix in c("", ":wave")) {
      for (level in names(CONDITION_CODES)) {
        w <- slope_weights("condition", CONDITION_CODES[[level]], suffix)
        label <- paste0("slope_", level, if (nzchar(suffix)) "_by_wave")
        estimates <- rbind(estimates, contrast_row(m, w, label))
      }
    }
  } else {
    estimates <- fit_estimates(fits[[name]], "condition", CONDITION_CODES)
  }
  add(name, "retained", estimates, fits[[name]])
}


# The other answer rule
# Accuracy without timeouts (the ladder walked from the top); response times of all answered
# questions, correct and incorrect, with outliers removed the same way (refit from the reported
# rung).

fit <- fit_ladder(ladder("is_correct", FIXED), retained[!retained$is_timed_out, ], "binomial",
                  RUNG)
add("accuracy_timeouts_dropped", "retained", fit_estimates(fit, "condition", CONDITION_CODES), fit)
fit <- fit_ladder(ladder("log_rt", FIXED), rt_frame(retained, answered = TRUE), "gaussian",
                  RUNG, from = RUNG)
add("rt_all_answered", "retained", fit_estimates(fit, "condition", CONDITION_CODES), fit)


# Participant-level randomization tests
# Per participant: mean accuracy over every main question; mean log RT over the response-time
# model's answers; least-squares slope of accuracy (one point per distance) on `log_distance`;
# least-squares slope of log RT on `log_distance + trial` (at least four answers, at two or more
# distances). Participants come in order of assignment_id compared as text ("100" before "55"),
# the order of the reported randomization p values.

participant_values <- function(d) {
  r <- rt_frame(d)
  values <- lapply(levels(droplevels(d$participant)), function(id) {
    a <- d[d$participant == id, , drop = FALSE]
    b <- r[r$participant == id, , drop = FALSE]
    by_distance <- stats::aggregate(list(accuracy = a$is_correct),
                                    list(log_distance = a$log_distance), mean)
    rt_slope <- NA
    if (nrow(b) >= 4 && length(unique(b$log_distance)) >= 2) {
      rt_slope <- stats::coef(stats::lm(log_rt ~ log_distance + trial, data = b))[["log_distance"]]
    }
    data.frame(participant = id, assignment_id = a$assignment_id[1],
               condition = condition_name(a$condition[1]), accuracy_mean = mean(a$is_correct),
               rt_mean = if (nrow(b)) mean(b$log_rt) else NA,
               accuracy_slope = stats::coef(stats::lm(accuracy ~ log_distance,
                                                      data = by_distance))[["log_distance"]],
               rt_slope = rt_slope, stringsAsFactors = FALSE)
  })
  values <- do.call(rbind, values)
  values[order(as.character(values$assignment_id)), , drop = FALSE]
}

# Shuffled minus congruent in participant means (condition) and slopes (condition:log_distance),
# and the mean slope in each condition.
participant_tests <- function(per_participant, outcome) {
  mean_col <- paste0(outcome, "_mean")
  slope_col <- paste0(outcome, "_slope")
  pick <- function(col, level) {
    v <- per_participant[[col]][per_participant$condition == level]
    v[!is.na(v)]
  }
  rbind(welch_row("condition", pick(mean_col, "congruent"), pick(mean_col, "shuffled")),
        welch_row("condition:log_distance", pick(slope_col, "congruent"),
                  pick(slope_col, "shuffled")),
        one_sample_row("slope_congruent", pick(slope_col, "congruent")),
        one_sample_row("slope_shuffled", pick(slope_col, "shuffled")))
}

values <- list(retained = participant_values(retained))
values$all_finishers <- participant_values(main_questions("all_finishers"))
for (set in SETS) {
  for (o in names(outcomes)) {
    add(paste0(o, "_participant_level"), set, participant_tests(values[[set]], o))
  }
}


# Leaving out one participant at a time
# Each model refit without each participant at the reported formula. Counted: refits that fail
# strict mode (their estimates are kept), refits whose estimate changes sign, and refits whose p
# crosses .05. The refits take participant levels in order of assignment_id compared as text:
# this order reproduces results/experiment2/models.csv (the order moves the fits slightly; in
# numeric order the accuracy refit without P061 fails to converge).

for (o in names(outcomes)) {
  x <- outcomes[[o]]
  full <- fit_ladder(ladder(x$dv, FIXED), x$data, x$family, RUNG, from = RUNG)
  full_table <- coefficient_rows(full$model, full$summary)
  full_table <- full_table[match(TERMS, full_table$term), ]
  by_text <- x$data
  ids <- as.character(by_text$participant)
  text_order <- order(as.character(by_text$assignment_id))
  by_text$participant <- factor(ids, levels = unique(ids[text_order]))
  refits <- parallel::mclapply(unique(ids), function(id) {
    d <- by_text[by_text$participant != id, , drop = FALSE]
    d$participant <- droplevels(d$participant)
    d$item_pair <- droplevels(d$item_pair)
    r <- fit_rung(full$formula, d, x$family)
    if (is.null(r$model)) {
      stop(sprintf("Without %s: %s", id, paste(r$problems, collapse = "; ")), call. = FALSE)
    }
    coefs <- coefficient_rows(r$model, r$summary)
    k <- match(TERMS, coefs$term)
    list(estimate = coefs$estimate[k], p = coefs$p_value[k],
         problem = if (length(r$problems)) r$problems[[1]] else NA_character_)
  }, mc.cores = cores(8))
  check_jobs(refits, unique(ids))
  estimate <- sapply(refits, function(r) r$estimate)
  p <- sapply(refits, function(r) r$p)
  problem <- sapply(refits, function(r) r$problem)
  for (k in which(!is.na(problem))) {
    message(sprintf("%s: the refit without %s fails strict mode: %s", o, unique(ids)[k],
                    problem[k]))
  }
  counts <- data.frame(term = c("refits", "refits_failing_strict_mode"),
                       estimate = c(length(refits), sum(!is.na(problem))))
  for (k in seq_along(TERMS)) {
    flips <- sum(sign(estimate[k, ]) != sign(full_table$estimate[k]))
    crossings <- sum((p[k, ] < 0.05) != (full_table$p_value[k] < 0.05))
    counts <- rbind(counts, data.frame(term = paste0(TERMS[k], c("_sign_changes", "_crossings")),
                                       estimate = c(flips, crossings)))
  }
  counts[c("std_error", "df", "statistic", "p_value", "conf_low", "conf_high")] <- NA
  add(paste0(o, "_leave_one_out"), "retained", counts, full)
}


# Lee bounds
# Bounds on the shuffled minus congruent difference in the participant values above, allowing
# for unequal retention between the conditions. Population: everyone who reached the main
# questions (condition is assigned before them), one row per participant from their primary
# session (most saved rows, then lowest assignment_id, then earliest), in participant order;
# kept = in the set. The condition with higher retention q_hi is trimmed by (q_hi - q_lo) / q_hi
# from the top or the bottom of its values (a fractional weight on the boundary value).
# Bootstrap: participants resampled within condition, everything recomputed. Rows: <term> is the
# difference among kept participants; <term>_lower_bound and <term>_upper_bound are the bounds,
# with the 95% CI of the bounds as conf_low of the lower (its 2.5th percentile) and conf_high of
# the upper (its 97.5th percentile).

trimmed_mean <- function(x, p, from) {
  x <- sort(x, decreasing = (from == "bottom"))
  K <- (1 - p) * length(x)
  if (!length(x) || K <= 0) return(NA_real_)
  sum(pmin(pmax(K - (seq_along(x) - 1), 0), 1) * x) / K
}

lee_once <- function(y, kept, condition) {
  qc <- mean(kept[condition == "congruent"])
  qs <- mean(kept[condition == "shuffled"])
  yc <- y[kept & condition == "congruent"]
  ys <- y[kept & condition == "shuffled"]
  if (!length(yc) || !length(ys)) return(c(lower = NA, upper = NA))
  if (qc > qs) {
    p <- (qc - qs) / qc
    return(c(lower = mean(ys) - trimmed_mean(yc, p, "bottom"),
             upper = mean(ys) - trimmed_mean(yc, p, "top")))
  }
  if (qs > qc) {
    p <- (qs - qc) / qs
    return(c(lower = trimmed_mean(ys, p, "top") - mean(yc),
             upper = trimmed_mean(ys, p, "bottom") - mean(yc)))
  }
  c(lower = mean(ys) - mean(yc), upper = mean(ys) - mean(yc))
}

lee_bounds <- function(y, kept, condition) {
  bounds <- lee_once(y, kept, condition)
  ic <- which(condition == "congruent")
  ish <- which(condition == "shuffled")
  set.seed(SEED)
  draws <- sapply(seq_len(N_BOOTSTRAP), function(b) {
    i <- c(ic[sample.int(length(ic), length(ic), replace = TRUE)],
           ish[sample.int(length(ish), length(ish), replace = TRUE)])
    lee_once(y[i], kept[i], condition[i])
  })
  ok <- !is.na(draws["lower", ]) & !is.na(draws["upper", ])
  c(bounds, conf_low = unname(stats::quantile(draws["lower", ok], 0.025)),
    conf_high = unname(stats::quantile(draws["upper", ok], 0.975)))
}

sessions <- read_input("sessions")
primary <- sessions[order(sessions$participant, -sessions$n_saved_rows, sessions$assignment_id,
                          sessions$session_index), ]
primary <- primary[!duplicated(primary$participant), ]
population <- primary[primary$n_main_questions > 0, ]
for (set in SETS) {
  kept <- population[[set]]
  if (!setequal(population$participant[kept], values[[set]]$participant)) {
    stop(sprintf("The %s participants differ from the primary sessions in the set.", set),
         call. = FALSE)
  }
  for (o in names(outcomes)) {
    estimates <- NULL
    for (term in c("condition", "condition:log_distance")) {
      col <- paste0(o, if (term == "condition") "_mean" else "_slope")
      y <- values[[set]][[col]][match(population$participant, values[[set]]$participant)]
      if (anyNA(y[kept])) stop(sprintf("A %s participant has no %s.", set, col), call. = FALSE)
      b <- lee_bounds(y, kept, population$condition)
      difference <- mean(y[kept & population$condition == "shuffled"]) -
        mean(y[kept & population$condition == "congruent"])
      estimates <- rbind(estimates, data.frame(
        term = paste0(term, c("", "_lower_bound", "_upper_bound")),
        estimate = c(difference, b[["lower"]], b[["upper"]]),
        conf_low = c(NA, b[["conf_low"]], NA), conf_high = c(NA, NA, b[["conf_high"]])))
    }
    estimates[c("std_error", "df", "statistic", "p_value")] <- NA
    add(paste0(o, "_lee_bounds"), set, estimates)
  }
}


# Codings of symbolic distance
# Each coding centered over the six distances: log; linear; two-piece (a step from 1 to 2 and a
# slope beyond 2); categorical (sum-coded, distance 6 is -1 on every column). Maximum-likelihood
# fits with the reported random effects; the condition-by-distance interaction is tested by a
# likelihood-ratio test against the model without it.

codings <- list(
  log = function(x) data.frame(log_distance = log(x) - mean(log(DISTANCES))),
  linear = function(x) data.frame(linear_distance = x - mean(DISTANCES)),
  two_piece = function(x) data.frame(distance_step = (x >= 2) - mean(DISTANCES >= 2),
                                     distance_beyond_2 = pmax(x - 2, 0) -
                                       mean(pmax(DISTANCES - 2, 0))),
  categorical = function(x) {
    k <- length(DISTANCES)
    columns <- stats::contr.sum(k)[match(x, DISTANCES), , drop = FALSE]
    stats::setNames(as.data.frame(columns), paste0("distance_", DISTANCES[-k]))
  })

# The fits run in parallel, one job per outcome, coding and model (full or reduced).
jobs <- list()
for (o in names(outcomes)) {
  x <- outcomes[[o]]
  for (coding in names(codings)) {
    coded <- codings[[coding]](x$data$symbolic_distance)
    d <- x$data
    d[names(coded)] <- coded
    cols <- names(coded)
    D <- if (length(cols) == 1) cols else sprintf("(%s)", paste(cols, collapse = " + "))
    f <- c(full = sprintf("%s ~ condition * %s + trial + %s", x$dv, D, RANDOM),
           reduced = sprintf("%s ~ condition + %s + trial + %s", x$dv,
                             paste(cols, collapse = " + "), RANDOM))
    for (model in names(f)) {
      jobs[[paste(o, coding, model)]] <- list(formula = f[[model]], data = d, family = x$family,
                                              df = length(cols))
    }
  }
}
ll <- parallel::mclapply(jobs, function(j) {
  r <- fit_rung(j$formula, j$data, j$family, REML = FALSE)
  if (length(r$problems)) {
    stop(sprintf("%s: %s", j$formula, paste(r$problems, collapse = "; ")), call. = FALSE)
  }
  as.numeric(stats::logLik(r$model))
}, mc.cores = cores(8))
check_jobs(ll)
for (o in names(outcomes)) {
  for (coding in names(codings)) {
    full <- paste(o, coding, "full")
    chisq <- 2 * (ll[[full]] - ll[[paste(o, coding, "reduced")]])
    k <- jobs[[full]]$df
    test <- data.frame(term = coding, estimate = NA, std_error = NA, df = k,
                       statistic = chisq, p_value = stats::pchisq(chisq, k, lower.tail = FALSE),
                       conf_low = NA, conf_high = NA)
    add(paste0(o, "_distance_codings"), "retained", test,
        list(formula = jobs[[full]]$formula, rung = RUNG))
  }
}

checks <- c("_waves", "_without_round_2", "_participant_level", "_leave_one_out", "_lee_bounds",
            "_distance_codings")
write_results(rows, c(as.vector(outer(names(outcomes), checks, paste0)),
                      "accuracy_timeouts_dropped", "rt_all_answered"))
