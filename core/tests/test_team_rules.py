"""Team rules: [[rules]] in lockstep.toml, the team_rules hook and check_team_rules."""

import json
import subprocess
from pathlib import Path

import pytest

from lockstep_checks.check_team_rules import check_team_rules
from lockstep_checks.config import ConfigError, load_config
from lockstep_checks.gitdiff import ChangedFile
from lockstep_checks.hooks import Event, team_rules

SHIM = Path(__file__).resolve().parents[1] / "hooks" / "run-hook.sh"

RULES = """\
[enforcement]
default = "enforce"

[[rules]]
name = "no-select-star"
pattern = '(?i)select\\s+\\*'
paths = ["models/**/*.sql"]
message = "List the columns."

[[rules]]
name = "uv-not-pip"
on = "command"
pattern = '^\\s*pip3? install\\b'
message = "Use uv add."
"""


@pytest.fixture
def rules_repo(repo):
    repo.commit({"lockstep.toml": RULES, "models/a.sql": "select id from x\n"})
    return repo


def edit(root, rel, tool="Write", **args):
    return Event({"tool_name": tool, "tool_input": {"file_path": str(root / rel), **args}, "cwd": str(root)})


def bash(root, command):
    return Event({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)})


# config


def test_rules_load_with_defaults(tmp_path):
    (tmp_path / "lockstep.toml").write_text(RULES)
    star, pip = load_config(tmp_path).rules
    assert (star.name, star.on, star.paths) == ("no-select-star", "content", ("models/**/*.sql",))
    assert (pip.on, pip.paths) == ("command", ("**",))


@pytest.mark.parametrize(
    ("toml", "fragment"),
    [
        ("[rules]\nname = 'x'\n", "must be written as \\[\\[rules\\]\\]"),
        ("[[rules]]\nname = 'x'\npattern = 'a'\n", "needs message"),
        ("[[rules]]\nname = 'x'\npattern = 'a'\nmessage = 'm'\nseverity = 'high'\n", "unknown key rules.severity"),
        ("[[rules]]\nname = 'No Caps'\npattern = 'a'\nmessage = 'm'\n", "lower-case words"),
        ("[[rules]]\nname = 'x'\npattern = '('\nmessage = 'm'\n", "not a valid regex"),
        ("[[rules]]\nname = 'x'\non = 'file'\npattern = 'a'\nmessage = 'm'\n", "on must be one of content, command"),
        ("[[rules]]\nname = 'x'\non = 'command'\npattern = 'a'\nmessage = 'm'\npaths = ['a']\n", "content rules only"),
        (
            "[[rules]]\nname = 'x'\npattern = 'a'\nmessage = 'm'\n[[rules]]\nname = 'x'\npattern = 'b'\nmessage = 'm'\n",
            "unique",
        ),
    ],
)
def test_bad_rules_are_config_errors(tmp_path, toml, fragment):
    (tmp_path / "lockstep.toml").write_text(toml)
    with pytest.raises(ConfigError, match=fragment):
        load_config(tmp_path)


# check


def test_check_flags_added_lines_under_the_rule_paths(tmp_path):
    (tmp_path / "lockstep.toml").write_text(RULES)
    cfg = load_config(tmp_path)
    files = [
        ChangedFile("models/b.sql", "A", added_lines=((1, "with x as ("), (2, "  SELECT * from y"))),
        ChangedFile("scripts/adhoc.sql", "A", added_lines=((1, "select * from y"),)),
        ChangedFile("models/c.sql", "M", added_lines=((4, "pip install x"),)),
    ]
    found = check_team_rules(files, cfg)
    assert [(f.path, f.line, f.message) for f in found] == [
        ("models/b.sql", 2, "rule no-select-star: List the columns.")
    ]


# hook


def test_hook_blocks_content_a_rule_forbids(rules_repo):
    d = team_rules.hook(edit(rules_repo.root, "models/b.sql", content="select *\nfrom x\n"))
    assert d.block and "no-select-star (models/b.sql): List the columns." in d.message


def test_hook_reads_edits_multiedits_and_patches(rules_repo):
    root = rules_repo.root
    assert team_rules.hook(edit(root, "models/a.sql", "Edit", old_string="id", new_string="*, select * ")).block
    multi = edit(
        root, "models/a.sql", "MultiEdit", edits=[{"old_string": "a", "new_string": "ok"}, {"new_string": "SELECT *"}]
    )
    assert team_rules.hook(multi).block
    patch = "*** Begin Patch\n*** Update File: models/a.sql\n@@\n-select id from x\n+select * from x\n*** End Patch\n"
    copilot = Event({"tool_name": "Edit", "tool_input": {"input": patch}, "cwd": str(root)})
    assert team_rules.hook(copilot).block
    removed_only = patch.replace("+select * from x\n", "+select id, name from x\n")
    assert not team_rules.hook(
        Event({"tool_name": "Edit", "tool_input": {"input": removed_only}, "cwd": str(root)})
    ).block


def test_hook_allows_paths_outside_the_rule_and_outside_the_repo(rules_repo, tmp_path):
    root = rules_repo.root
    assert not team_rules.hook(edit(root, "scripts/adhoc.sql", content="select * from x")).block
    outside = Event(
        {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.sql", "content": "select *"}, "cwd": str(root)}
    )
    assert not team_rules.hook(outside).block


def test_hook_blocks_commands_a_rule_forbids(rules_repo):
    root = rules_repo.root
    d = team_rules.hook(bash(root, "cd src && \n  pip install requests"))
    assert d.block and "uv-not-pip: Use uv add." in d.message
    assert not team_rules.hook(bash(root, "uv add requests")).block


def test_hook_does_nothing_without_rules(repo):
    repo.commit({"models/a.sql": "x\n"})
    assert not team_rules.hook(edit(repo.root, "models/a.sql", content="select *")).block


def test_shim_runs_team_rules(rules_repo):
    payload = {"tool_name": "Bash", "tool_input": {"command": "pip install x"}, "cwd": str(rules_repo.root)}
    p = subprocess.run(
        ["bash", str(SHIM), "team_rules"], input=json.dumps(payload), capture_output=True, text=True, check=False
    )
    assert p.returncode == 2 and "uv-not-pip" in p.stderr
