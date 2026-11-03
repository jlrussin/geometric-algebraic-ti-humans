# Shared code of the Experiment 2 models, sourced by models.R, agree_conflict.R, robustness.R and
# manipulation_check.R (each run from the repository root): inputs, design coding, the
# response-time rule, the random-effects ladder, fitting, inference, randomization tests, the
# results table and the random-effects table.

suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
})

INPUT_DIR <- file.path("analysis", "inputs", "experiment2")
RESULTS_CSV <- file.path("results", "experiment2", "models.csv")
RESULT_COLUMNS <- c("experiment", "model", "set", "formula", "rung", "term", "estimate",
                    "std_error", "df", "statistic", "p_value", "conf_low", "conf_high")
RANDOM_EFFECTS_CSV <- file.path("results", "experiment2", "random_effects.csv")
RANDOM_EFFECT_COLUMNS <- c("experiment", "model", "set", "group", "term1", "term2", "estimate",
                           "observations", "participants")
SETS <- c("retained", "all_finishers")

# Design: six symbolic distances, 48 main questions per participant.
DISTANCES <- 1:6
QUESTIONS <- 48
CONDITION_CODES <- c(congruent = -0.5, shuffled = 0.5)
TYPE_CODES <- c(agree = -0.5, conflict = 0.5)
WAVE_CODES <- c(-0.5, 0.5)    # waves 1 and 2
RT_Z_CUTOFF <- 3

SINGULAR_TOL <- 1e-4
LMER_CONTROL <- lmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
GLMER_CONTROL <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))

N_DRAWS <- 10000    # randomization tests: seeded draws
SEED <- 1

# Cores for parallel refits: at most `n`, leaving two free; one core on Windows, where forking
# is not available.
cores <- function(n) {
  available <- parallel::detectCores()
  if (.Platform$OS.type == "windows" || is.na(available)) return(1L)
  max(1L, min(n, available - 2L))
}

# Stops on the first parallel job that failed or returned nothing (its worker was killed),
# naming the job. mclapply hands out jobs in fixed batches, one per worker, so a job that fails
# also fails the jobs of its batch; the message then shows the failing job's own error.
check_jobs <- function(results, jobs = names(results)) {
  for (i in seq_along(results)) {
    job <- if (is.null(jobs)) as.character(i) else jobs[[i]]
    if (is.null(results[[i]])) {
      stop(sprintf("Job %s returned nothing: its worker stopped.", job), call. = FALSE)
    }
    if (inherits(results[[i]], "try-error")) {
      stop(sprintf("Job %s: %s", job, results[[i]]), call. = FALSE)
    }
  }
}


# Inputs and coding

read_input <- function(table) {
  path <- file.path(INPUT_DIR, paste0(table, ".parquet"))
  if (!file.exists(path)) {
    stop(sprintf("%s is missing: run `geo-alg-ti-humans prepare` first.", path), call. = FALSE)
  }
  as.data.frame(nanoparquet::read_parquet(path))
}

# The main questions of a participant set, coded for the models, with each session's wave and
# allocation round. Every participant of the set must have all 48 questions.
main_questions <- function(set) {
  s <- read_input("sessions")
  d <- read_input("trials")
  kept <- s$participant[s[[set]]]
  if (anyDuplicated(kept)) {
    stop(sprintf("More than one %s session per participant.", set), call. = FALSE)
  }
  d <- d[d[[set]], , drop = FALSE]
  n <- table(d$participant)
  if (!setequal(names(n), kept) || any(n != QUESTIONS)) {
    stop(sprintf("Not every %s participant has %d main questions.", set, QUESTIONS),
         call. = FALSE)
  }
  if (!setequal(d$symbolic_distance, DISTANCES) || anyNA(d$is_correct) || anyNA(d$is_timed_out)) {
    stop("Unexpected symbolic distances, or a missing is_correct or is_timed_out.", call. = FALSE)
  }
  k <- match(paste(d$participant, d$session_index), paste(s$participant, s$session_index))
  d$wave <- s$wave[k]
  d$allocation_round <- s$allocation_round[k]
  code_design(d)
}

# Numeric predictors (so `||` removes the correlation):
#   condition     shuffled +0.5, congruent -0.5
#   type          conflict +0.5, agree -0.5 (used in the shuffled condition)
#   log_distance  ln d minus the mean of ln d over the six distances
#   trial         (question number - 24.5) / 10
#   wave          wave 2 +0.5, wave 1 -0.5
# Rows are in order of assignment_id and question number, and participant levels follow
# assignment_id (numeric): this order reproduces results/experiment2/models.csv (row and level
# order move some fits in the fourth decimal).
code_design <- function(d) {
  d <- d[order(d$assignment_id, d$question_number), , drop = FALSE]
  rownames(d) <- NULL
  d$participant <- factor(d$participant, levels = unique(d$participant))
  d$item_pair <- factor(d$item_pair)
  d$condition <- unname(CONDITION_CODES[d$condition])
  if (anyNA(d$condition)) stop("A condition other than congruent or shuffled.", call. = FALSE)
  d$type <- unname(TYPE_CODES[d$question_type])
  if (anyNA(d$type[d$condition == CONDITION_CODES[["shuffled"]]])) {
    stop("A shuffled question whose type is not agree or conflict.", call. = FALSE)
  }
  d$log_distance <- log(d$symbolic_distance) - mean(log(DISTANCES))
  d$trial <- (d$question_number - (QUESTIONS + 1) / 2) / 10
  if (anyNA(d$wave) || !all(d$wave %in% seq_along(WAVE_CODES))) {
    stop("Every session needs a wave of 1 or 2.", call. = FALSE)
  }
  d$wave <- WAVE_CODES[d$wave]
  d$is_correct <- as.integer(d$is_correct)
  d
}

condition_name <- function(code) names(CONDITION_CODES)[match(code, CONDITION_CODES)]

shuffled_only <- function(d) d[d$condition == CONDITION_CODES[["shuffled"]], , drop = FALSE]

zscore <- function(v) {
  if (length(v) > 1 && stats::sd(v) > 0) (v - mean(v)) / stats::sd(v) else rep(0, length(v))
}

# Response times of the models: correct answers (not timed out, with a response time), natural
# log, removing answers whose log response time has |z| > 3 within participant (SD with n - 1).
# answered = TRUE keeps incorrect answers too, with outliers removed the same way.
rt_frame <- function(d, answered = FALSE) {
  r <- d[!d$is_timed_out & !is.na(d$rt) & (answered | d$is_correct == 1L), , drop = FALSE]
  if (any(r$rt <= 0)) stop("A response time that is not positive.", call. = FALSE)
  r$log_rt <- log(r$rt)
  z <- stats::ave(r$log_rt, as.character(r$participant), FUN = zscore)
  r[abs(z) <= RT_Z_CUTOFF, , drop = FALSE]
}


# The random-effects ladder

# Random-effects structures from richest to simplest:
#   1. (1 + log_distance | participant) + (1 | item_pair)
#   2. (1 + log_distance || participant) + (1 | item_pair)
#   3. (1 + log_distance | participant)
#   4. (1 | participant) + (1 | item_pair)
#   5. (1 | participant)
# `top` adds two rungs above them with more participant slopes (correlated, then uncorrelated).
ladder <- function(dv, fixed, top = NULL) {
  with_slopes <- function(s) c(sprintf("(1 + %s | participant) + (1 | item_pair)", s),
                               sprintf("(1 + %s || participant) + (1 | item_pair)", s),
                               sprintf("(1 + %s | participant)", s))
  random <- c(with_slopes("log_distance"), "(1 | participant) + (1 | item_pair)",
              "(1 | participant)")
  if (!is.null(top)) random <- c(with_slopes(paste(top, collapse = " + "))[1:2], random)
  paste(dv, "~", fixed, "+", random)
}

# One fit in strict mode: it fails on an error, any warning or message (the summary included),
# a singular fit or a convergence message. Returns the model and its summary (NULL on an error)
# and the problems.
fit_rung <- function(formula, data, family, REML = TRUE) {
  problems <- character(0)
  note <- function(kind, text) problems <<- c(problems, paste0(kind, ": ", trimws(text)))
  fitted <- withCallingHandlers(
    tryCatch({
      f <- stats::as.formula(formula)
      m <- if (family == "binomial") {
        glmer(f, data = data, family = stats::binomial, control = GLMER_CONTROL)
      } else {
        lmerTest::lmer(f, data = data, REML = REML, control = LMER_CONTROL)
      }
      list(model = m, summary = summary(m))
    }, error = function(e) {
      note("error", conditionMessage(e))
      NULL
    }),
    warning = function(w) {
      note("warning", conditionMessage(w))
      invokeRestart("muffleWarning")
    },
    message = function(m) {
      note("message", conditionMessage(m))
      invokeRestart("muffleMessage")
    })
  model <- fitted$model
  if (!is.null(model)) {
    if (isSingular(model, tol = SINGULAR_TOL)) note("fit", "singular")
    for (msg in unlist(model@optinfo$conv$lme4$messages)) note("convergence", msg)
  }
  list(model = model, summary = fitted$summary, problems = unique(problems))
}

# Fits the ladder from rung `from` down; the first rung to pass strict mode must be `rung`, the
# rung reported for this model, else the script stops.
fit_ladder <- function(formulas, data, family, rung, from = 1) {
  for (i in seq(from, length(formulas))) {
    r <- fit_rung(formulas[i], data, family)
    if (!length(r$problems)) break
  }
  if (length(r$problems)) {
    stop(sprintf("%s: no rung from %d down passes strict mode (last: %s).", formulas[rung],
                 from, paste(r$problems, collapse = "; ")), call. = FALSE)
  }
  if (i != rung) {
    stop(sprintf("%s: rung %d of %d passes strict mode, not the reported rung %d.",
                 formulas[i], i, length(formulas), rung), call. = FALSE)
  }
  list(model = r$model, summary = r$summary, formula = formulas[i], rung = i)
}


# Refits from the reported rung, in parallel: each job names its `dv`, `fixed` effects, `data`
# and `family`, and each must pass strict mode at `rung`. Returns the fits by job name.
refit_at_rung <- function(jobs, rung, top = NULL) {
  fits <- parallel::mclapply(jobs, function(j) {
    fit_ladder(ladder(j$dv, j$fixed, top), j$data, j$family, rung, from = rung)
  }, mc.cores = cores(4))
  check_jobs(fits)
  fits
}


# Inference

# Fixed effects with Wald z (glmer) or Satterthwaite t (lmer); 95% CI = estimate +/- t SE, with
# the normal quantile for z. df is NA for z. `s` is the model's summary, if already computed.
coefficient_rows <- function(model, s = summary(model)) {
  cf <- s$coefficients
  wald <- inherits(model, "glmerMod")
  df <- if (wald) rep(Inf, nrow(cf)) else unname(cf[, "df"])
  estimate_rows(rownames(cf), unname(cf[, "Estimate"]), unname(cf[, "Std. Error"]), df,
                unname(cf[, if (wald) "z value" else "t value"]),
                unname(cf[, if (wald) "Pr(>|z|)" else "Pr(>|t|)"]))
}

estimate_rows <- function(term, estimate, se, df, statistic, p) {
  half <- stats::qt(0.975, df) * se
  data.frame(term = term, estimate = estimate, std_error = se, df = ifelse(is.finite(df), df, NA),
             statistic = statistic, p_value = p, conf_low = estimate - half,
             conf_high = estimate + half, stringsAsFactors = FALSE)
}

# Coefficient names compared with the parts of an interaction in any order.
term_key <- function(term) {
  vapply(strsplit(term, ":", fixed = TRUE), function(p) paste(sort(p), collapse = ":"), "")
}

# A linear combination of the fixed effects, `weights` named by term: Wald z (glmer) or
# lmerTest's Satterthwaite t (lmer).
contrast_row <- function(model, weights, term) {
  beta <- fixef(model)
  k <- match(term_key(names(weights)), term_key(names(beta)))
  if (anyNA(k)) {
    stop(sprintf("No term %s in the model.", paste(names(weights)[is.na(k)], collapse = ", ")),
         call. = FALSE)
  }
  L <- stats::setNames(rep(0, length(beta)), names(beta))
  L[k] <- L[k] + unname(weights)
  if (inherits(model, "glmerMod")) {
    est <- sum(L * beta)
    se <- sqrt(as.numeric(t(L) %*% as.matrix(stats::vcov(model)) %*% L))
    return(estimate_rows(term, est, se, Inf, est / se, 2 * stats::pnorm(-abs(est / se))))
  }
  ct <- lmerTest::contest1D(model, L)
  estimate_rows(term, ct$Estimate, ct$`Std. Error`, ct$df, ct$`t value`, ct$`Pr(>|t|)`)
}

# Weights of the log-distance slope at code `code` of `by` (condition or type); with `suffix`
# ":wave", the slope's interaction with wave.
slope_weights <- function(by, code, suffix = "") {
  stats::setNames(c(1, code), paste0(c("log_distance", paste0(by, ":log_distance")), suffix))
}

# The log-distance slope at each level of `by`, named slope_<level>: the contrast above, whose
# estimate and standard error are checked against emmeans::emtrends to 1e-6 (the check compares
# no degrees of freedom, so emtrends uses the asymptotic ones).
slope_rows <- function(model, by, codes) {
  do.call(rbind, lapply(names(codes), function(level) {
    row <- contrast_row(model, slope_weights(by, codes[[level]]), paste0("slope_", level))
    at <- stats::setNames(list(unname(codes[[level]]), 0), c(by, "trial"))
    e <- emmeans::emtrends(model, stats::as.formula(paste("~", by)), var = "log_distance",
                           at = at, lmer.df = "asymptotic")
    s <- as.data.frame(summary(e, infer = c(TRUE, TRUE)))
    differ <- c(s$log_distance.trend[1] - row$estimate, s$SE[1] - row$std_error)
    if (any(abs(differ) > 1e-6)) {
      stop(sprintf("emtrends and the contrast disagree on slope_%s.", level), call. = FALSE)
    }
    row
  }))
}

# A fit's coefficient rows followed by its distance slope at each level of `by`.
fit_estimates <- function(fit, by, codes) {
  rbind(coefficient_rows(fit$model, fit$summary), slope_rows(fit$model, by, codes))
}


# Randomization tests (two-sided, 10,000 seeded draws)
#
# The draws are paired with the values by position, so a p value depends on the order of the
# values; each caller states the order it uses.

# Relabeling of the two groups x and y on stat(x, y):
# p = (1 + relabelings with |stat - center| >= the observed) / (1 + 10,000).
relabel_test <- function(x, y, stat, center = 0) {
  v <- c(x, y)
  observed <- stat(x, y)
  tol <- 1e-12 * max(1, abs(observed - center))
  set.seed(SEED)
  s <- replicate(N_DRAWS, {
    idx <- sample.int(length(v), length(y))
    stat(v[-idx], v[idx])
  })
  list(statistic = observed,
       p = (1 + sum(abs(s - center) >= abs(observed - center) - tol)) / (1 + N_DRAWS))
}

# Sign flips of the values (null: distributed symmetrically about 0): p = (1 + draws with
# |mean| >= the observed) / (1 + 10,000); the same test on the one-sample t, a monotone function
# of |mean| under sign flips.
signflip_test <- function(v) {
  observed <- mean(v)
  tol <- 1e-12 * max(1, abs(observed))
  set.seed(SEED)
  signs <- matrix(sample(c(-1, 1), N_DRAWS * length(v), replace = TRUE), nrow = N_DRAWS)
  means <- as.numeric(signs %*% v) / length(v)
  (1 + sum(abs(means) >= abs(observed) - tol)) / (1 + N_DRAWS)
}

# Shuffled minus congruent participant values: Welch t, its 95% CI and df, and the
# randomization p of the Welch t statistic.
welch_row <- function(term, congruent, shuffled) {
  tt <- stats::t.test(shuffled, congruent, var.equal = FALSE)
  welch_t <- function(x, y) (mean(y) - mean(x)) / sqrt(stats::var(x) / length(x) +
                                                       stats::var(y) / length(y))
  p <- relabel_test(congruent, shuffled, welch_t)$p
  data.frame(term = term, estimate = mean(shuffled) - mean(congruent), std_error = NA,
             df = unname(tt$parameter), statistic = unname(tt$statistic), p_value = p,
             conf_low = tt$conf.int[1], conf_high = tt$conf.int[2], stringsAsFactors = FALSE)
}

# Mean of participant values against 0: one-sample t, its 95% CI and df, and the sign-flip p.
one_sample_row <- function(term, v) {
  tt <- stats::t.test(v, mu = 0)
  data.frame(term = term, estimate = mean(v), std_error = NA, df = unname(tt$parameter),
             statistic = unname(tt$statistic), p_value = signflip_test(v),
             conf_low = tt$conf.int[1], conf_high = tt$conf.int[2], stringsAsFactors = FALSE)
}


# Results table

# Rows of results/experiment2/models.csv for one model and set; `fit` is NULL for results that
# are not a model fit.
result_rows <- function(model, set, rows, fit = NULL) {
  data.frame(experiment = 2L, model = model, set = set,
             formula = if (is.null(fit)) NA_character_ else fit$formula,
             rung = if (is.null(fit)) NA_integer_ else fit$rung,
             rows[, setdiff(RESULT_COLUMNS, c("experiment", "model", "set", "formula", "rung"))],
             stringsAsFactors = FALSE)
}

as_text <- function(x) {
  out <- if (is.numeric(x)) vapply(x, format, "", digits = 15) else as.character(x)
  out[is.na(x)] <- ""
  out
}

# Replaces this script's models in the results table and writes it sorted by model, set and the
# term order of each fit, numbers to 15 significant digits.
write_results <- function(rows, models) {
  new <- do.call(rbind, rows)
  if (!all(new$model %in% models)) {
    stop("A result row belongs to another script's models.", call. = FALSE)
  }
  new <- as.data.frame(lapply(new[RESULT_COLUMNS], as_text), stringsAsFactors = FALSE)
  if (file.exists(RESULTS_CSV)) {
    old <- utils::read.csv(RESULTS_CSV, colClasses = "character", na.strings = character(0))
    new <- rbind(old[!(old$model %in% models), RESULT_COLUMNS, drop = FALSE], new)
  }
  if (anyDuplicated(new[c("model", "set", "term")])) {
    stop("Duplicate (model, set, term) rows.", call. = FALSE)
  }
  if (any(grepl("[,\"\n]", unlist(new)))) stop("A field would need quoting.", call. = FALSE)
  new <- new[order(new$model, new$set, seq_len(nrow(new)), method = "radix"), ]
  dir.create(dirname(RESULTS_CSV), recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(new, RESULTS_CSV, row.names = FALSE, quote = FALSE)
}

# Rows of results/experiment2/random_effects.csv for one fitted model: the SD of each random
# term, then the correlation of each pair of correlated terms, then the residual SD of a linear
# model (term2 empty for an SD), with the numbers of observations and participants. lme4 names the
# groups of uncorrelated terms participant, participant.1, ...; each is written under its grouping
# factor.
random_effect_rows <- function(model, set, fitted) {
  vc <- as.data.frame(VarCorr(fitted), order = "lower.tri")
  key <- ifelse(vc$grp == "Residual", 2L, ifelse(is.na(vc$var2), 0L, 1L))
  vc <- vc[order(key, seq_len(nrow(vc)), method = "radix"), , drop = FALSE]
  data.frame(experiment = 2L, model = model, set = set,
             group = ifelse(vc$grp == "Residual", "residual", sub("[.][0-9]+$", "", vc$grp)),
             term1 = vc$var1, term2 = vc$var2, estimate = vc$sdcor,
             observations = stats::nobs(fitted),
             participants = unname(ngrps(fitted)[["participant"]]), stringsAsFactors = FALSE)
}

# Writes the random-effects table, which only models.R writes, sorted by model and set.
write_random_effects <- function(rows) {
  new <- do.call(rbind, rows)
  new <- as.data.frame(lapply(new[RANDOM_EFFECT_COLUMNS], as_text), stringsAsFactors = FALSE)
  if (any(grepl("[,\"\n]", unlist(new)))) stop("A field would need quoting.", call. = FALSE)
  new <- new[order(new$model, new$set, seq_len(nrow(new)), method = "radix"), ]
  dir.create(dirname(RANDOM_EFFECTS_CSV), recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(new, RANDOM_EFFECTS_CSV, row.names = FALSE, quote = FALSE)
}
