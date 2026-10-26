"""PRs into a feature branch carry the spec's tests red on purpose; everything else must pass."""

from lockstep_checks.red_phase import expected_red, is_test_file, main


def feature_with_red_tests(repo):
    repo.commit({"tests/test_old.py": "def test_old():\n    assert 1\n", "src/app.py": "x = 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("feature/0042-churn")
    repo.commit(
        {"tests/test_churn.py": "def test_churn():\n    assert 0\n", "tests/conftest.py": "", "src/churn.py": ""}
    )
    repo.commit({"tests/test_old.py": "def test_old():\n    assert 2\n"})
    return repo


def test_into_a_feature_branch_only_the_new_test_files_may_be_red(repo):
    feature_with_red_tests(repo)
    assert expected_red(repo.root, "refs/heads/feature/0042-churn") == ["tests/test_churn.py"]


def test_into_main_nothing_is_excused(repo):
    feature_with_red_tests(repo)
    assert expected_red(repo.root, "refs/heads/main") == []
    assert expected_red(repo.root, "") == []


def test_test_file_names():
    assert is_test_file("tests/test_a.py") and is_test_file("a_test.py")
    assert not is_test_file("tests/conftest.py") and not is_test_file("tests/test_a.yml")


def test_cli_prints_one_file_per_line(repo, capsys):
    feature_with_red_tests(repo)
    assert main(["--root", str(repo.root), "--target", "feature/0042-churn"]) == 0
    assert capsys.readouterr().out == "tests/test_churn.py\n"
