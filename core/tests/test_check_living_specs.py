from pathlib import Path

from lockstep_checks.check_living_specs import HEADER, check_living_specs, main
from lockstep_checks.config import load_config

ON = "[specs]\nliving = true\n"


def spec_md(title: str, criteria: str) -> str:
    return (
        f"---\nid: x\ntitle: {title}\n---\n\n# {title}\n\n## 1. P\n## 2. S\n## 3. Acceptance criteria\n{criteria}"
        "## 4. I\n## 5. T\n## 6. R\n## 7. Open questions\n"
    )


def add_spec(root: Path, folder: str, state: str, capability: str | None, criteria: str, title="Churn score") -> None:
    d = root / "specs" / folder
    d.mkdir(parents=True)
    (d / "spec.md").write_text(spec_md(title, criteria), encoding="utf-8")
    lock = "locked_at_commit: abc1234\n" if state in ("tests-locked", "implemented") else ""
    cap = f"capability: {capability}\n" if capability else ""
    (d / "status.yml").write_text(
        f"status: {state}\npii: no\ntrack: data\njira: MXAAI-1\n{lock}{cap}", encoding="utf-8"
    )


def setup(root: Path, toml: str = ON) -> Path:
    (root / "lockstep.toml").write_text(toml, encoding="utf-8")
    add_spec(
        root,
        "0042-churn-score",
        "implemented",
        "churn-scoring",
        "- AC-001 THE model SHALL score every customer.\n- ~~AC-002~~ superseded by 0057/AC-001\n",
    )
    add_spec(
        root,
        "0057-daily-churn",
        "approved",
        "churn-scoring",
        "- AC-001 Daily scores\n  - WHEN the day ends\n  - THEN every customer has a new score\n",
        title="Daily churn",
    )
    add_spec(root, "0059-locked", "tests-locked", "churn-scoring", "- AC-001 THE model SHALL explain a score.\n", "Why")
    add_spec(root, "0060-draft", "draft", None, "- AC-001 THE x SHALL y.\n")
    return root


def check(root: Path, write=False):
    return check_living_specs(root, load_config(root), write)


def test_off_by_default(tmp_path):
    setup(tmp_path, toml="")
    assert check(tmp_path) == []


def test_missing_living_spec_fails_until_written(tmp_path):
    setup(tmp_path)
    [finding] = check(tmp_path)
    assert finding.level == "error" and finding.path == "specs/living/churn-scoring.md"
    assert "is missing; run `python -m lockstep_checks.check_living_specs --write`" in finding.message
    assert check(tmp_path, write=True) == []
    assert check(tmp_path) == []


def test_living_spec_shows_what_is_in_force_and_coming(tmp_path):
    setup(tmp_path)
    check(tmp_path, write=True)
    text = (tmp_path / "specs/living/churn-scoring.md").read_text(encoding="utf-8")
    assert text.startswith(HEADER + "\n\n# churn-scoring\n")
    assert (
        "## In force\n\n### [0042 Churn score](../0042-churn-score/spec.md) (implemented)\n\n"
        "- 0042/AC-001 THE model SHALL score every customer.\n"
    ) in text
    assert "### [0059 Why](../0059-locked/spec.md) (tests-locked)\n\n- 0059/AC-001" in text.split("## Coming")[0]
    assert "AC-002" not in text  # superseded
    assert (
        "## Coming\n\n### [0057 Daily churn](../0057-daily-churn/spec.md) (approved)\n\n"
        "- 0057/AC-001 Daily scores\n  - WHEN the day ends\n  - THEN every customer has a new score\n"
    ) in text
    assert "0060" not in text  # drafts stay out


def test_spec_change_makes_it_stale(tmp_path):
    setup(tmp_path)
    check(tmp_path, write=True)
    md = tmp_path / "specs/0042-churn-score/spec.md"
    md.write_text(md.read_text().replace("every customer.", "every active customer."))
    assert "out of date" in check(tmp_path)[0].message


def test_capability_without_specs_is_removed(tmp_path):
    setup(tmp_path)
    check(tmp_path, write=True)
    old = tmp_path / "specs/living/old-capability.md"
    old.write_text(HEADER + "\n# old\n")
    (tmp_path / "specs/living/README.md").write_text("hand-written notes\n")
    assert "no spec names this capability any more" in check(tmp_path)[0].message
    check(tmp_path, write=True)
    assert not old.exists() and (tmp_path / "specs/living/README.md").exists()


def test_hand_written_file_is_never_overwritten(tmp_path):
    setup(tmp_path)
    (tmp_path / "specs/living").mkdir()
    mine = tmp_path / "specs/living/churn-scoring.md"
    mine.write_text("# mine\n")
    assert "was not generated" in check(tmp_path, write=True)[0].message
    assert mine.read_text() == "# mine\n"


def test_spec_past_draft_needs_a_capability(tmp_path):
    setup(tmp_path)
    add_spec(tmp_path, "0070-no-cap", "approved", None, "- AC-001 THE x SHALL y.\n")
    messages = [f.message for f in check(tmp_path, write=True)]
    assert messages == [
        "spec 0070 names no capability; add `capability: <name>` to status.yml so its criteria reach a living spec"
    ]


def test_cli_warn_mode_and_write(tmp_path, capsys):
    setup(tmp_path, toml=ON + '[enforcement]\ndefault = "warn"\n')
    assert main(["--root", str(tmp_path), "--base", "HEAD", "--branch", "main"]) == 0
    assert "would block (warn mode)" in capsys.readouterr().out
    assert main(["--root", str(tmp_path), "--base", "HEAD", "--branch", "main", "--write"]) == 0
    assert (tmp_path / "specs/living/churn-scoring.md").is_file()
