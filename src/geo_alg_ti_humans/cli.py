"""Command line: ``geo-alg-ti-humans <verb>``.

Verbs:
  images      download the PicturePerfectSet archive, verify it, and crop the 80 Experiment 1
              images into ``experiments/experiment1/media/pps/``
  prepare     apply the exclusions, build the participant sets and response-time frames, and
              write the inputs to the R models
  regenerate  replay every session's trial sequence from its assignment and compare it with the
              trials table
  numbers     write ``results/numbers.csv``: every number the paper prints about the two
              experiments' participants, trials, statistics and models, recomputed and compared
              with the printed value
  stats-tables
              write ``results/stats_tables/``: a LaTeX table of each of the paper's main
              mixed-effects models, from the R results
  figure      draw one figure into ``figures/out/``: ``figure --name <topic>``
  smoke       run ``prepare``, the summaries and every figure (not the R models) on the small
              synthetic tables in ``tests/synthetic/``
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

FIGURE_TOPICS = ("learning", "pairs", "arbitrage", "participants", "participant_slopes",
                 "robustness", "agree_conflict", "strategies", "participants_congruent",
                 "participants_shuffled")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser: one subcommand per verb."""
    parser = argparse.ArgumentParser(
        prog="geo-alg-ti-humans",
        description="Human experiments: stimuli, data preparation, trial regeneration, "
        "numbers, statistics tables and figures.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    images = sub.add_parser("images", help="download, verify and crop the Experiment 1 images")
    images.add_argument("--archive", type=Path,
                        help="a copy of Clipart_JPG.zip to use instead of downloading")
    sub.add_parser("prepare", help="exclusions, participant sets, response-time frames, R inputs")
    sub.add_parser("regenerate", help="replay every session's trial sequence and compare it")
    sub.add_parser("numbers",
                   help="recompute every number the paper prints about the two experiments")
    sub.add_parser("stats-tables",
                   help="write a LaTeX table of each of the paper's main mixed-effects models")
    figure = sub.add_parser("figure", help="draw one figure")
    figure.add_argument("--name", required=True, choices=FIGURE_TOPICS)
    sub.add_parser("smoke", help="prepare, summarize and draw from the synthetic tables")
    return parser


def _message(error: Exception) -> str:
    """The message of ``error``; a ``KeyError``'s without the quotes its text adds."""
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error)


def _checkout() -> Path:
    """The repository the package runs from; raises ``FileNotFoundError`` in an installed copy,
    which has no ``experiments/``, ``analysis/``, ``results/`` or ``figures/`` to work in."""
    from geo_alg_ti_humans import REPO_ROOT

    if not (REPO_ROOT / "pyproject.toml").is_file():
        raise FileNotFoundError("the package is not running from a repository checkout")
    return REPO_ROOT


def images(args: argparse.Namespace) -> int:
    """Crop the 80 images into ``experiments/experiment1/media/pps/``; return 1 on failure."""
    import sys
    import zipfile
    from http.client import HTTPException

    from geo_alg_ti_humans.images import build

    try:
        media_dir = _checkout() / "experiments" / "experiment1" / "media" / "pps"
        written = build(media_dir, archive=args.archive)
    except (HTTPException, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"images: {_message(error)}", file=sys.stderr)
        return 1
    print(f"{len(written)} images in {media_dir}, each matching its digest in media.sha256")
    return 0


def _count_line(counts) -> str:
    """``name n, ...`` for every nonzero count, in the order given."""
    return ", ".join(f"{name} {n:,}" for name, n in counts if n)


def _prepare_report(experiment1: tuple, experiment2: tuple) -> list[str]:
    """The kept and per-reason counts and the response-time frame counts, as printed lines.

    ``experiment1`` and ``experiment2`` are what ``prepare.load_experiment1`` and
    ``prepare.load_experiment2`` return.
    """
    from geo_alg_ti_humans import prepare as prep

    sessions, trials, exclusions = experiment1
    reasons = exclusions["reason"].value_counts()
    rows = prep.kept_rows(trials, exclusions)
    rows = rows[rows["phase"].isin(prep.TASK_PHASES)]
    frame = prep.rt_frame_experiment1_models(rows)
    flagged = frame["rt_trimmed"].astype(bool)
    by_phase = _count_line(
        (p, int((flagged & (frame["phase"] == p)).sum())) for p in prep.TASK_PHASES)
    lines = [
        f"experiment1: {len(exclusions)} sessions of {sessions['participant'].nunique()} people, "
        f"{int(exclusions['reason'].isna().sum())} kept",
        "  excluded sessions: " + _count_line(
            (r, int(reasons.get(r, 0))) for r in prep.REASONS_EXPERIMENT1),
        f"  response times for the models: {len(rows):,} learning and test rows, "
        f"{len(frame):,} correct and answered (all arbitrage-test rows), "
        f"{int((~flagged).sum()):,} kept",
        f"    outliers: {int(flagged.sum())} ({by_phase})",
    ]

    sessions, trials, _, sets = experiment2
    lines.append(f"experiment2: {len(sessions)} sessions of {sessions['participant'].nunique()} "
                 "people")
    for name, exclusions in sets.items():
        lines.append(f"  {name}:")
        for condition in ("congruent", "shuffled"):
            mine = exclusions[exclusions["condition"] == condition]
            counts = mine["reason"].value_counts()
            lines.append(f"    {condition}: {int(mine['reason'].isna().sum())} kept; excluded "
                         "sessions: " + _count_line(
                             (r, int(counts.get(r, 0))) for r in prep.REASONS_EXPERIMENT2))
        frame = prep.rt_trimmed_experiment2(prep.kept_rows(trials, exclusions))
        answered = ~prep.as_bool(frame["is_timed_out"], "response times for the figures")
        flagged = frame["rt_trimmed"].astype(bool)
        correct = prep.rt_kept_experiment2(frame)
        lines.append(f"    response times for the figures: {int(answered.sum()):,} answered, "
                     f"{int(flagged.sum())} outliers, {int(correct.sum()):,} correct and kept")
    return lines


def prepare(args: argparse.Namespace) -> int:
    """Write the R inputs to ``analysis/inputs/`` and print the exclusion and response-time
    counts; return 1 if the tables cannot be read or prepared."""
    import sys

    from geo_alg_ti_humans import prepare as prep

    try:
        out_dir = _checkout() / "analysis" / "inputs"
        first, second = prep.load_experiment1(), prep.load_experiment2()
        paths = prep.write_r_inputs(out_dir, experiment1=first, experiment2=second)
        lines = _prepare_report(first, second)
    except (OSError, KeyError, ValueError) as error:
        print(f"prepare: {_message(error)}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    print(f"{len(paths)} R input tables in {out_dir}")
    return 0


def regenerate(args: argparse.Namespace) -> int:
    """Replay and compare every session of both experiments; return 1 on a difference or failure.

    A failed replay ends that experiment's comparison; the other experiment is still compared.
    """
    import sys

    from geo_alg_ti_humans import regenerate as replay
    from geo_alg_ti_humans.tables import EXPERIMENTS

    try:
        _checkout()
    except OSError as error:
        print(f"regenerate: {_message(error)}", file=sys.stderr)
        return 1
    status = 0
    for experiment in EXPERIMENTS:
        try:
            report = replay.run(experiment)
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            print(f"regenerate: {experiment}: {_message(error)}", file=sys.stderr)
            status = 1
            continue
        print(f"{experiment}: {report.n_sessions} sessions, {report.n_matched} matched, "
              f"{report.n_without_plan} without planned rows, "
              f"{len(report.differences)} differences")
        shown = report.differences[:20]
        for line in shown:
            print(f"  {line}")
        if len(report.differences) > len(shown):
            print(f"  ... and {len(report.differences) - len(shown)} more")
        if not report.ok:
            status = 1
    return status


def numbers(args: argparse.Namespace) -> int:
    """Write ``results/numbers.csv``; return 1 if any number differs from the paper."""
    import sys

    from geo_alg_ti_humans import summaries

    try:
        path = _checkout() / "results" / "numbers.csv"
        table = summaries.numbers()
    except (OSError, KeyError, ValueError) as error:
        print(f"numbers: {_message(error)}", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, lineterminator="\n")
    differ = table[~table["match"]]
    print(f"{len(table)} numbers, {len(table) - len(differ)} as printed; wrote {path}")
    for row in differ.itertuples():
        print(f"  {row.id} ({row.site}): printed {row.printed}, computed {row.computed}")
    return 1 if len(differ) else 0


def stats_tables(args: argparse.Namespace) -> int:
    """Write the LaTeX tables into ``results/stats_tables/``; return 1 if the R results cannot
    be read or tabulated."""
    import sys

    from geo_alg_ti_humans.stats_tables import write_tables

    try:
        results = _checkout() / "results"
        written = write_tables(results, results / "stats_tables")
    except (OSError, KeyError, ValueError) as error:
        print(f"stats-tables: {_message(error)}", file=sys.stderr)
        return 1
    print(f"{len(written)} tables in {results / 'stats_tables'}")
    return 0


def _figure_module(stem: str):
    """The module ``figures/<stem>.py``, imported with ``figures/`` on ``sys.path``.

    The figure scripts import their helpers as ``_shared``, which then resolves as it does when
    a script is run directly.
    """
    import importlib
    import sys

    figures = _checkout() / "figures"
    if str(figures) not in sys.path:
        sys.path.insert(0, str(figures))
    return importlib.import_module(stem)


def figure(args: argparse.Namespace) -> int:
    """Draw the figure ``args.name`` into ``figures/out/``; return 1 if it cannot be drawn.

    Runs ``figures/fig_<name>.py`` as it runs with no arguments: on the data tables (the
    directory named by ``GEO_ALG_TI_HUMANS_DATA`` if set, else ``data/``), writing a PDF and a
    PNG preview.
    """
    import sys

    try:
        script = _figure_module(f"fig_{args.name}")
        _figure_module("_shared").main(script.build, name=script.NAME, argv=[])
    except (OSError, KeyError, ValueError) as error:
        print(f"figure: {_message(error)}", file=sys.stderr)
        return 1
    return 0


def smoke(args: argparse.Namespace) -> int:
    """Run the data preparation, the summaries and every figure on the synthetic tables; return 1
    if a step fails.

    Runs ``prepare`` (the exclusions, participant sets, response-time frames and R inputs), the
    counts and descriptive statistics of ``summaries``, and ``figure`` for every topic, on the
    small synthetic tables in ``tests/synthetic/``, whose responses are random, so the values are
    not the paper's. The R models are not run. Everything is written to a temporary directory,
    removed at the end. Prints one line per step.
    """
    import contextlib
    import io
    import sys
    import tempfile

    from geo_alg_ti_humans import REPO_ROOT, summaries, tables
    from geo_alg_ti_humans import prepare as prep

    root = REPO_ROOT / "tests" / "synthetic"
    if not (root / tables.MANIFEST).is_file():
        print(f"smoke: no synthetic tables in {root}", file=sys.stderr)
        return 1
    try:
        shared = _figure_module("_shared")
        with tempfile.TemporaryDirectory(prefix="geo-alg-ti-humans-smoke-") as tmp:
            out_dir = Path(tmp)
            first, second = prep.load_experiment1(root), prep.load_experiment2(root)
            paths = prep.write_r_inputs(out_dir / "inputs", experiment1=first, experiment2=second)
            totals = [line for line in _prepare_report(first, second) if not line.startswith(" ")]
            print(f"prepare: {len(paths)} R input tables; " + "; ".join(totals))
            for name, values in summaries.summary_values(experiment1=first,
                                                         experiment2=second).items():
                print(f"summaries.{name}: {len(values)} values")
            for topic in FIGURE_TOPICS:
                script = _figure_module(f"fig_{topic}")
                with contextlib.redirect_stdout(io.StringIO()):
                    written = shared.main(script.build, name=script.NAME, argv=[
                        "--data", str(root), "--out", str(out_dir / "figures")])
                print(f"figure {topic}: " + ", ".join(path.name for path in written))
    except (OSError, KeyError, ValueError) as error:
        print(f"smoke: {_message(error)}", file=sys.stderr)
        return 1
    print("smoke: every step ran on the synthetic tables")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, run the verb, and return its exit code."""
    args = build_parser().parse_args(argv)
    return HANDLERS[args.verb](args)


HANDLERS = {
    "images": images,
    "prepare": prepare,
    "regenerate": regenerate,
    "numbers": numbers,
    "stats-tables": stats_tables,
    "figure": figure,
    "smoke": smoke,
}
