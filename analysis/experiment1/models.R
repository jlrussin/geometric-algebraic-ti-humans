# Fits the six Experiment 1 mixed-effects models and writes their fixed effects to
# results/experiment1/models.csv and their random effects to results/experiment1/random_effects.csv.
# Run from the repository root after `geo-alg-ti-humans prepare`.

INPUTS <- file.path("analysis", "inputs", "experiment1")
OUTPUT <- file.path("results", "experiment1", "models.csv")
RANDOM_OUTPUT <- file.path("results", "experiment1", "random_effects.csv")
COLUMNS <- c(
  "experiment", "model", "set", "formula", "rung", "term", "estimate", "std_error", "df",
  "statistic", "p_value", "conf_low", "conf_high"
)
RANDOM_COLUMNS <- c(
  "experiment", "model", "set", "group", "term1", "term2", "estimate", "observations",
  "participants"
)
SINGULAR_TOL <- 1e-4

# Random-effects structures by participant, from the maximal one down. `phase` is coded 0 (ICL
# test) and 1 (IWL test) as a number, so that `||` removes every correlation.
DISTANCE_LADDER <- c("(1 + symbolic_distance | participant)", "(1 | participant)")
INTERACTION_LADDER <- c(
  "(1 + symbolic_distance * phase | participant)",
  "(1 + symbolic_distance * phase || participant)",
  "(1 + symbolic_distance + phase | participant)",
  "(1 + symbolic_distance | participant)",
  "(1 | participant)"
)

# Accuracy uses every ICL and IWL test trial (a timeout counts as incorrect); log RT uses the
# correct test trials left after outlier removal. `rung` is the rung each model reaches, as
# reported.
MODELS <- list(
  icl_accuracy = list(input = "trials", phases = "icl_test", n_rows = 1600L, rung = 1L),
  iwl_accuracy = list(input = "trials", phases = "iwl_test", n_rows = 1600L, rung = 1L),
  accuracy_by_test = list(input = "trials", phases = c("icl_test", "iwl_test"), n_rows = 3200L,
                          rung = 1L),
  icl_rt = list(input = "rt", phases = "icl_test", n_rows = 1251L, rung = 1L),
  iwl_rt = list(input = "rt", phases = "iwl_test", n_rows = 1223L, rung = 1L),
  rt_by_test = list(input = "rt", phases = c("icl_test", "iwl_test"), n_rows = 2474L, rung = 2L)
)

if (!file.exists(file.path("analysis", "experiment1", "models.R"))) {
  stop("run this script from the repository root", call. = FALSE)
}
# Loaded here so that a warning on loading cannot count as a failed fit.
for (package in c("lme4", "lmerTest", "broom.mixed", "nanoparquet")) loadNamespace(package)

read_input <- function(name) {
  path <- file.path(INPUTS, paste0(name, ".parquet"))
  if (!file.exists(path)) {
    stop(path, " is missing: run `geo-alg-ti-humans prepare` first", call. = FALSE)
  }
  as.data.frame(nanoparquet::read_parquet(path))
}

# Logistic model for accuracy, linear model (REML) for log RT.
fit <- function(formula, data, binomial) {
  formula <- stats::as.formula(formula)
  if (binomial) {
    control <- lme4::glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
    lme4::glmer(formula, data = data, family = stats::binomial, control = control)
  } else {
    control <- lme4::lmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
    lmerTest::lmer(formula, data = data, REML = TRUE, control = control)
  }
}

# One fit in strict mode, as in Experiment 2: it fails on an error, any warning or message (the
# summary included), a singular fit or a convergence message. Returns the model (NULL on an
# error) and the problems.
fit_rung <- function(formula, data, binomial) {
  problems <- character(0)
  note <- function(kind, text) problems <<- c(problems, paste0(kind, ": ", trimws(text)))
  model <- withCallingHandlers(
    tryCatch({
      m <- fit(formula, data, binomial)
      summary(m)
      m
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
    }
  )
  if (!is.null(model)) {
    if (lme4::isSingular(model, tol = SINGULAR_TOL)) note("fit", "singular")
    for (msg in unlist(model@optinfo$conv$lme4$messages)) note("convergence", msg)
  }
  list(model = model, problems = unique(problems))
}

# The first rung that passes strict mode.
fit_ladder <- function(fixed, ladder, data, binomial) {
  for (rung in seq_along(ladder)) {
    formula <- paste(fixed, "+", ladder[[rung]])
    r <- fit_rung(formula, data, binomial)
    if (!length(r$problems)) return(list(model = r$model, formula = formula, rung = rung))
    last <- paste(r$problems, collapse = "; ")
  }
  stop("no rung of the ladder passes strict mode for ", fixed, " (last rung: ", last, ")",
    call. = FALSE)
}

# Wald z and normal 95% CIs for the logistic models; Satterthwaite t, df and t-based 95% CIs
# for the linear ones.
coefficient_rows <- function(model) {
  tidy <- broom.mixed::tidy(model, effects = "fixed", conf.int = TRUE)
  df <- if (inherits(model, "glmerMod")) NA_real_ else tidy$df
  data.frame(
    term = tidy$term, estimate = tidy$estimate, std_error = tidy$std.error, df = df,
    statistic = tidy$statistic, p_value = tidy$p.value, conf_low = tidy$conf.low,
    conf_high = tidy$conf.high
  )
}

# The SD of each random term, then the correlation of each pair of correlated terms, then the
# residual SD of a linear model (term2 empty for an SD), with the numbers of observations and
# participants. lme4 names the groups of uncorrelated terms participant, participant.1, ...; each
# is written under its grouping factor, participant.
random_effect_rows <- function(model) {
  vc <- as.data.frame(lme4::VarCorr(model), order = "lower.tri")
  key <- ifelse(vc$grp == "Residual", 2L, ifelse(is.na(vc$var2), 0L, 1L))
  vc <- vc[order(key, seq_len(nrow(vc)), method = "radix"), , drop = FALSE]
  data.frame(
    group = ifelse(vc$grp == "Residual", "residual", sub("[.][0-9]+$", "", vc$grp)),
    term1 = ifelse(is.na(vc$var1), "", vc$var1), term2 = ifelse(is.na(vc$var2), "", vc$var2),
    estimate = vc$sdcor, observations = stats::nobs(model),
    participants = unname(lme4::ngrps(model)[["participant"]])
  )
}

as_text <- function(x) {
  if (is.character(x)) return(ifelse(is.na(x), "", x))
  vapply(x, function(v) if (is.na(v)) "" else format(v, digits = 15), "")
}

csv_line <- function(fields) {
  quoted <- grepl("[\",\n]", fields)
  fields[quoted] <- paste0("\"", gsub("\"", "\"\"", fields[quoted]), "\"")
  paste(fields, collapse = ",")
}

inputs <- list(trials = read_input("trials"), rt = read_input("rt"))
rows <- list()
random_rows <- list()
for (name in names(MODELS)) {
  spec <- MODELS[[name]]
  data <- inputs[[spec$input]]
  data <- data[data$phase %in% spec$phases, , drop = FALSE]
  response <- if (spec$input == "trials") "is_correct" else "log_rt"
  if (nrow(data) != spec$n_rows) {
    stop(name, ": expected ", spec$n_rows, " rows, found ", nrow(data), call. = FALSE)
  }
  incomplete <- sum(!stats::complete.cases(
    data[c(response, "symbolic_distance", "phase", "participant")]
  ))
  if (incomplete > 0) {
    stop(name, ": missing values in ", incomplete, " of ", nrow(data), " rows", call. = FALSE)
  }
  binomial <- response == "is_correct"
  if (binomial) data$is_correct <- as.integer(data$is_correct)
  data$phase <- as.numeric(data$phase == "iwl_test")

  by_test <- length(spec$phases) == 2L
  fixed <- paste(response, "~", if (by_test) "symbolic_distance * phase" else "symbolic_distance")
  ladder <- if (by_test) INTERACTION_LADDER else DISTANCE_LADDER
  result <- fit_ladder(fixed, ladder, data, binomial)
  cat(sprintf("%s: rung %d of %d\n", name, result$rung, length(ladder)))
  if (result$rung != spec$rung) {
    stop(name, " reached rung ", result$rung, ", not rung ", spec$rung, " as reported",
      call. = FALSE)
  }
  rows[[name]] <- data.frame(
    experiment = 1L, model = name, set = "", formula = result$formula, rung = result$rung,
    coefficient_rows(result$model)
  )
  random_rows[[name]] <- data.frame(experiment = 1L, model = name, set = "",
                                    random_effect_rows(result$model))
}

# A stable sort keeps each model's rows in the order they were made.
write_rows <- function(rows, columns, path) {
  table <- do.call(rbind, lapply(rows, function(r) as.data.frame(lapply(r[columns], as_text))))
  table <- table[order(table$model, table$set, method = "radix"), , drop = FALSE]
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  writeLines(c(csv_line(columns), apply(table, 1, csv_line)), path)
  cat("wrote ", path, "\n", sep = "")
}
write_rows(rows, COLUMNS, OUTPUT)
write_rows(random_rows, RANDOM_COLUMNS, RANDOM_OUTPUT)
