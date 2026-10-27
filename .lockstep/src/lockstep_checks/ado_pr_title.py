"""Read the PR title in Azure Pipelines and pass it to the checks as ``LOCKSTEP_PR_TITLE``.

Azure Pipelines has no built-in variable for the PR title, but the `[large-approved]` and
`[test-change]` overrides live in it. This step asks the Azure DevOps REST API with the
job's ``System.AccessToken`` and sets the variable for the steps after it:

  - script: python -m lockstep_checks.ado_pr_title
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)

Outside a PR build it does nothing. If the API call fails the step fails, because the
checks would otherwise ignore an override the author asked for.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import TextIO

from .cli import TITLE_ENV

API_VERSION = "7.1"
_NEEDED = ("SYSTEM_COLLECTIONURI", "SYSTEM_TEAMPROJECTID", "BUILD_REPOSITORY_ID", "SYSTEM_ACCESSTOKEN")

Fetch = Callable[[urllib.request.Request], bytes]


class TitleError(RuntimeError):
    """The title could not be read."""


def pr_url(env: Mapping[str, str]) -> str:
    base = env["SYSTEM_COLLECTIONURI"].rstrip("/")
    return (
        f"{base}/{env['SYSTEM_TEAMPROJECTID']}/_apis/git/repositories/{env['BUILD_REPOSITORY_ID']}"
        f"/pullRequests/{env['SYSTEM_PULLREQUEST_PULLREQUESTID']}?api-version={API_VERSION}"
    )


def fetch_title(env: Mapping[str, str], fetch: Fetch | None = None) -> str:
    missing = [name for name in _NEEDED if not env.get(name)]
    if missing:
        hint = (
            " Map it in the step: env: SYSTEM_ACCESSTOKEN: $(System.AccessToken)."
            if "SYSTEM_ACCESSTOKEN" in missing
            else ""
        )
        raise TitleError(f"missing pipeline variables: {', '.join(missing)}.{hint}")
    req = urllib.request.Request(
        pr_url(env), headers={"Authorization": f"Bearer {env['SYSTEM_ACCESSTOKEN']}", "Accept": "application/json"}
    )
    try:
        body = (fetch or _urlopen)(req)
        title = json.loads(body)["title"]
    except urllib.error.HTTPError as e:
        raise TitleError(f"Azure DevOps API returned {e.code}. The build service needs Read on the repository.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TitleError(f"cannot reach Azure DevOps: {e}") from e
    except (ValueError, KeyError, TypeError) as e:
        raise TitleError("unexpected reply from the pull request API") from e
    if not isinstance(title, str):
        raise TitleError("unexpected reply from the pull request API")
    return title


def set_variable_command(title: str) -> str:
    # One line only: a newline would end the command and let the rest of the title run as a new one.
    # Line breaks become spaces instead of %0A escapes, which the agent decodes inconsistently.
    value = " ".join(title.splitlines())
    return f"##vso[task.setvariable variable={TITLE_ENV}]{value}"


def _urlopen(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main(env: Mapping[str, str] | None = None, out: TextIO | None = None, fetch: Fetch | None = None) -> int:
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out
    if not env.get("SYSTEM_PULLREQUEST_PULLREQUESTID"):
        print("ado_pr_title: not a PR build, nothing to do", file=out)
        return 0
    try:
        title = fetch_title(env, fetch)
    except TitleError as e:
        print(f"##vso[task.logissue type=error]ado_pr_title: {e}", file=out)
        return 1
    print(set_variable_command(title), file=out)
    print(f"ado_pr_title: {TITLE_ENV} set", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
