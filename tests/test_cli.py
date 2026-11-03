"""The command line: verbs, figure topics, and the smoke path."""

from __future__ import annotations

import pytest

from geo_alg_ti_humans import cli, tables


def test_parser_has_the_seven_verbs():
    """Every verb parses, and each has a handler."""
    parser = cli.build_parser()
    for verb in ("images", "prepare", "regenerate", "numbers", "stats-tables", "smoke"):
        assert parser.parse_args([verb]).verb == verb
    assert parser.parse_args(["figure", "--name", "learning"]).verb == "figure"
    assert set(cli.HANDLERS) == {"images", "prepare", "regenerate", "numbers", "stats-tables",
                                 "figure", "smoke"}


def test_figure_takes_a_known_topic():
    """``figure --name`` accepts the figure topics and nothing else."""
    parser = cli.build_parser()
    for topic in cli.FIGURE_TOPICS:
        assert parser.parse_args(["figure", "--name", topic]).name == topic
    with pytest.raises(SystemExit):
        parser.parse_args(["figure", "--name", "distance"])


def test_error_messages_print_without_the_quotes_of_a_key_error():
    """A missing key prints as its message, as every other error does."""
    assert cli._message(KeyError("no table 'x'")) == "no table 'x'"
    assert cli._message(ValueError("a value")) == "a value"


def test_smoke_runs_on_the_synthetic_tables(capsys):
    """``smoke`` prepares, summarizes and draws from the synthetic tables without error."""
    assert cli.main(["smoke"]) == 0
    out = capsys.readouterr().out
    assert "experiment1: 10 sessions of 9 people, 7 kept" in out
    for name in ("counts_experiment1", "descriptives_experiment1", "counts_experiment2",
                 "descriptives_experiment2"):
        assert f"summaries.{name}: " in out
    for topic in cli.FIGURE_TOPICS:
        assert f"figure {topic}: {topic}.pdf, {topic}.png" in out


def test_smoke_needs_the_synthetic_tables(tmp_path, monkeypatch, capsys):
    """Without ``tests/synthetic/``, as in an installed copy, ``smoke`` says so and fails."""
    import geo_alg_ti_humans

    monkeypatch.setattr(geo_alg_ti_humans, "REPO_ROOT", tmp_path)
    assert cli.main(["smoke"]) == 1
    assert "no synthetic tables" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["images"], ["prepare"], ["numbers"], ["stats-tables"],
                                  ["regenerate"], ["figure", "--name", "learning"]])
def test_verbs_working_in_the_repository_need_a_checkout(tmp_path, monkeypatch, capsys, argv):
    """In an installed copy, with no repository around the package, the verb says so in one
    line, fails, and writes nothing."""
    import geo_alg_ti_humans

    monkeypatch.setattr(geo_alg_ti_humans, "REPO_ROOT", tmp_path)
    assert cli.main(argv) == 1
    assert capsys.readouterr().err == (
        f"{argv[0]}: the package is not running from a repository checkout\n")
    assert not any(tmp_path.iterdir())


def test_figure_reports_a_failure_in_one_line(tmp_path, monkeypatch, capsys):
    """Without the data tables, ``figure`` prints one line naming the problem and fails."""
    monkeypatch.setenv(tables.DATA_ENV, str(tmp_path))
    assert cli.main(["figure", "--name", "learning"]) == 1
    assert capsys.readouterr().err == f"figure: no {tables.MANIFEST} in {tmp_path}\n"


def test_prepare_writes_the_r_inputs_and_reports_the_counts(data_root, tmp_path, monkeypatch,
                                                            capsys):
    """``prepare`` writes six tables under ``analysis/inputs/`` and prints the kept counts."""
    import geo_alg_ti_humans

    monkeypatch.setenv(tables.DATA_ENV, str(data_root))
    monkeypatch.setattr(geo_alg_ti_humans, "REPO_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    assert cli.main(["prepare"]) == 0
    assert len(list((tmp_path / "analysis" / "inputs").glob("experiment*/*.parquet"))) == 6
    out = capsys.readouterr().out
    assert "74 sessions of 65 people, 40 kept" in out
    assert "congruent: 49 kept" in out and "shuffled: 66 kept" in out


def test_numbers_writes_the_committed_table(data_root, repo_root, tmp_path, monkeypatch):
    """``numbers`` writes a table equal to the committed ``results/numbers.csv``."""
    import geo_alg_ti_humans

    monkeypatch.setenv(tables.DATA_ENV, str(data_root))
    monkeypatch.setattr(geo_alg_ti_humans, "REPO_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    assert cli.main(["numbers"]) == 0
    written = (tmp_path / "results" / "numbers.csv").read_text()
    assert written == (repo_root / "results" / "numbers.csv").read_text()
