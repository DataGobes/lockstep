import subprocess
from pathlib import Path

import pytest


class Repo:
    """A throwaway git repo: commit files on main, then on a PR branch."""

    def __init__(self, root: Path):
        self.root = root
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test Person 001")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def commit(self, files: dict[str, str | None], message: str = "change") -> None:
        for rel, text in files.items():
            p = self.root / rel
            if text is None:
                self.git("rm", "-q", rel)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            self.git("add", rel)
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)


@pytest.fixture
def repo(tmp_path) -> Repo:
    return Repo(tmp_path)
