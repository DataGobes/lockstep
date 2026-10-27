# Evidence artifacts collide, so the summary loses the quality evidence

## Expected
Each PR job that writes evidence publishes it under its own artifact name, so the summary job downloads all of them.
In a product repo's PR pipeline with the `lockstep` and `quality` jobs, the run has two artifacts, for example
`lockstep-evidence-checks` and `lockstep-evidence-quality`, and the summary lists every criterion with the result of
the test that names it.

## Actual
`lockstep-pr.yml`, `python-quality.yml` and `mutation-report.yml` all publish
`lockstep-evidence-$(System.JobName)`. In Azure DevOps build 229122 (the Lockstep repo's own PR pipeline, on PR 20086)
that resolved to `lockstep-evidence-__default` in two jobs. The second upload failed:

```
Artifact lockstep-evidence-__default already exists for build 229122.
```

The summary then said "Tests: not measured: no evidence from the quality step" and showed "no test" for every
criterion of spec 0003, although the tests had run.

## Criterion
`0001/AC-006`: the summary lists every criterion with each test that names it and that test's result in this run.

## Root cause
`core/pipelines/lockstep-pr.yml:54`, `core/pipelines/python-quality.yml:100` and
`core/pipelines/mutation-report.yml:60` name their artifact from a runtime variable, `$(System.JobName)`, which
was `__default` for more than one job in a run. The names are only unique if that variable is, and it isn't.

## Regression test
`core/tests/test_evidence_artifacts.py`. Before the fix:

```
E       AssertionError: assert {'lockstep-pr...tem.JobName)'} == {'lockstep-pr...ence-quality'}
E         Differing items:
E         {'python-quality.yml': 'lockstep-evidence-$(System.JobName)'} != {'python-quality.yml': 'lockstep-evidence-quality'}
E         {'mutation-report.yml': 'lockstep-evidence-$(System.JobName)'} != {'mutation-report.yml': 'lockstep-evidence-mutation'}
E         {'lockstep-pr.yml': 'lockstep-evidence-$(System.JobName)'} != {'lockstep-pr.yml': 'lockstep-evidence-checks'}
```

## Why the tests missed it
`core/tests/test_pipelines.py` checks parameters and template references statically; nothing checked artifact names,
and the unit tests of the summary read evidence folders that a test builds by hand. The collision only shows in a
real Azure DevOps run with more than one evidence job.
