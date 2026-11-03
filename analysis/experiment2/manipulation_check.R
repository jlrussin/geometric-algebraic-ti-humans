# Experiment 2 manipulation check: statements judged true by condition ("I don't know" excluded),
# Mann-Whitney test with a randomization p and the rank-biserial r, for both participant sets.
# Run from the repository root: Rscript analysis/experiment2/manipulation_check.R
source(file.path("analysis", "experiment2", "common.R"))

SCORES <- c("All of them" = 5, "Most of them" = 4, "About half of them" = 3, "Few of them" = 2,
            "None of them" = 1)
DONT_KNOW <- "I don't know"
# The reported numbers of participants who rated the statements, by set and condition; any
# other count stops.
RATED <- list(retained = c(congruent = 43, shuffled = 42),
              all_finishers = c(congruent = 43, shuffled = 56))

# x shuffled and y congruent scores, in participant order (the draws pair with it). W is the
# rank sum of y (midranks for ties), U = W - n_y (n_y + 1) / 2, and
# r = P(y > x) - P(y < x): positive when congruent participants judged more statements true.
mann_whitney <- function(x, y) {
  rank_sum <- function(a, b) sum(rank(c(a, b))[length(a) + seq_along(b)])
  test <- relabel_test(x, y, rank_sum, center = length(y) * (length(x) + length(y) + 1) / 2)
  r <- (sum(outer(y, x, ">")) - sum(outer(y, x, "<"))) / (length(x) * length(y))
  list(U = test$statistic - length(y) * (length(y) + 1) / 2, p = test$p, r = r)
}

questionnaire <- read_input("questionnaire")
questionnaire <- questionnaire[order(questionnaire$participant, questionnaire$session_index), ]
answers <- c(names(SCORES), DONT_KNOW)
if (!all(is.na(questionnaire$statements_true) | questionnaire$statements_true %in% answers)) {
  stop("Unexpected answers to statements_true.", call. = FALSE)
}
rows <- list()
for (set in SETS) {
  q <- questionnaire[questionnaire[[set]], , drop = FALSE]
  if (anyDuplicated(q$participant)) {
    stop(sprintf("More than one %s questionnaire per participant.", set), call. = FALSE)
  }
  score <- unname(SCORES[q$statements_true])
  congruent <- score[q$condition == "congruent" & !is.na(score)]
  shuffled <- score[q$condition == "shuffled" & !is.na(score)]
  rated <- c(congruent = length(congruent), shuffled = length(shuffled))
  if (any(rated != RATED[[set]])) {
    stop(sprintf("%s: %d congruent and %d shuffled ratings, not %d and %d.", set,
                 rated[[1]], rated[[2]], RATED[[set]][[1]], RATED[[set]][[2]]), call. = FALSE)
  }
  dont_know <- function(level) sum(q$statements_true[q$condition == level] %in% DONT_KNOW)
  test <- mann_whitney(shuffled, congruent)
  estimates <- data.frame(
    term = c("rank_biserial", "n_congruent", "n_shuffled", "dont_know_congruent",
             "dont_know_shuffled"),
    estimate = c(test$r, length(congruent), length(shuffled), dont_know("congruent"),
                 dont_know("shuffled")),
    std_error = NA, df = NA, statistic = c(test$U, NA, NA, NA, NA),
    p_value = c(test$p, NA, NA, NA, NA), conf_low = NA, conf_high = NA)
  rows[[length(rows) + 1]] <- result_rows("manipulation_check", set, estimates)
}
write_results(rows, "manipulation_check")
