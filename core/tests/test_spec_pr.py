import json

from lockstep_checks.spec_pr import main

SPEC = """\
## 1. Problem and outcome
## 2. Scope / non-goals
## 3. Acceptance criteria
{criteria}
## 4. Interfaces and data contract
## 5. Test and eval plan
## 6. Risks, rollout, rollback
## 7. Open questions
"""


def make(root, n_criteria: int, status_extra: str = "", toml: str = ""):
    if toml:
        (root / "lockstep.toml").write_text(f"[specs]\n{toml}\n")
    folder = root / "specs" / "0042-churn"
    folder.mkdir(parents=True)
    criteria = "\n".join(f"- AC-{i:03d} THE SYSTEM SHALL do {i}." for i in range(1, n_criteria + 1))
    (folder / "spec.md").write_text(SPEC.format(criteria=criteria))
    (folder / "status.yml").write_text(f"status: draft\npii: no\ntrack: data\n{status_extra}")


def run(root, capsys, *extra):
    assert main(["0042", "--root", str(root), *extra]) == 0
    return capsys.readouterr().out


def test_small_spec_goes_in_one_pr(tmp_path, capsys):
    make(tmp_path, 3)
    assert "goes in one PR with its failing tests" in run(tmp_path, capsys)


def test_reasons_are_listed_for_a_spec_pr(tmp_path, capsys):
    make(tmp_path, 9, "contract: yes\n")
    out = json.loads(run(tmp_path, capsys, "--json"))
    assert out["spec_pr"] is True
    assert len(out["reasons"]) == 2 and "9 criteria" in out["reasons"][0] and "contract" in out["reasons"][1]


def test_unknown_spec_is_an_error(tmp_path, capsys):
    assert main(["0099", "--root", str(tmp_path)]) == 1
    assert "no spec 0099" in capsys.readouterr().err
