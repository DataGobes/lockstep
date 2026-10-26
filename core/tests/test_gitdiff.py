from lockstep_checks.gitdiff import base_ref, changed_files


def test_reports_status_counts_and_added_lines(repo):
    repo.commit({"a.py": "x = 1\ny = 2\n", "old.py": "keep = 1\n" * 5, "gone.py": "z\n"})
    repo.branch("feature/0042-x")
    repo.commit({"a.py": "x = 1\ny = 3\nz = 4\n", "new.py": "n = 1\n", "gone.py": None})
    repo.git("mv", "old.py", "moved.py")
    repo.commit({})
    files = {f.path: f for f in changed_files(repo.root, "main")}

    assert files["a.py"].status == "M"
    assert (files["a.py"].added, files["a.py"].deleted) == (2, 1)
    assert files["a.py"].added_lines == ((2, "y = 3"), (3, "z = 4"))
    assert files["new.py"].status == "A" and not files["new.py"].existed_on_base
    assert files["gone.py"].status == "D" and files["gone.py"].added_lines == ()
    assert files["moved.py"].status == "R"
    assert files["moved.py"].base_path == "old.py"


def test_added_line_that_looks_like_a_header_is_content(repo):
    repo.commit({"a.sql": "select 1\n"})
    repo.branch("feature/0042-x")
    repo.commit({"a.sql": "select 1\n++ not a header\n"})
    (f,) = changed_files(repo.root, "main")
    assert f.added_lines == ((2, "++ not a header"),)


def test_base_ref_prefers_argument_then_pipeline_target():
    assert base_ref("develop", {}) == "develop"
    assert base_ref(None, {"SYSTEM_PULLREQUEST_TARGETBRANCH": "refs/heads/release/1"}) == "origin/release/1"
    assert base_ref(None, {}) == "origin/main"
