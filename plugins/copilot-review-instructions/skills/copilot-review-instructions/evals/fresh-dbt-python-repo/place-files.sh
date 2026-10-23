#!/usr/bin/env bash
# Copies the fixture and turns ./repo into a git repo with an Azure DevOps remote and some history.
set -eu
cp -R "$(dirname "$0")/files/." .
cd repo
git init -q -b main
git config user.email fixture@example.com
git config user.name fixture
git remote add origin https://dev.azure.com/contoso/data-platform/_git/sales-analytics
git add pyproject.toml README.md azure-pipelines.yml src tests dbt/dbt_project.yml dbt/packages.yml dbt/.sqlfluff dbt/macros
git commit -q -m "Initial ingest package and dbt project"
git add -A
git commit -q -m "Add staging, intermediate and finance marts"
