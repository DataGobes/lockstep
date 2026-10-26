import pytest

from lockstep_checks.paths import matches


@pytest.mark.parametrize(
    "path, pattern, expected",
    [
        ("tests/test_a.py", "tests/**", True),
        ("tests/unit/deep/test_a.py", "tests/**", True),
        ("src/tests/test_a.py", "tests/**", False),
        ("dbt/models/_x.unit_tests.yml", "**/*.unit_tests.yml", True),
        ("_x.unit_tests.yml", "**/*.unit_tests.yml", True),
        ("evals/thresholds.yml", "evals/thresholds.yml", True),
        ("evals/thresholds.yaml", "evals/thresholds.yml", False),
        ("src/a.py", "src/*.py", True),
        ("src/a/b.py", "src/*.py", False),
        ("a/__snapshots__/x.ambr", "**/__snapshots__/**", True),
        ("dbt\\target\\manifest.json", "**/manifest.json", True),
    ],
)
def test_matches(path, pattern, expected):
    assert matches(path, pattern) is expected
