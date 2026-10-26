#!/usr/bin/env bash
# Set main's branch policies for a Lockstep repo with the Azure DevOps CLI. Review it, fill in the variables, then
# run it yourself: it changes the repo's settings. Needs `az` with the azure-devops extension and `az login`.
# What each policy is for: docs/branch-policy.md.
set -euo pipefail

ORG="https://dev.azure.com/<organisation>"
PROJECT="<project>"
REPO="<repo>"
PR_PIPELINE="<name of the pipeline created from azure-pipelines-pr.yml>"
# Group (or user) ids that must approve changes to tests, evals, agent config and pipelines.
# Find a group id with: az devops security group list --project "$PROJECT" --query "graphGroups[].{name:displayName,id:originId}"
TEST_REVIEWERS="<id>"
BRANCH="main"

if grep -q '<' <<<"$ORG$PROJECT$REPO$PR_PIPELINE$TEST_REVIEWERS"; then
  echo "Fill in the variables at the top of $0 first." >&2
  exit 1
fi

az devops configure --defaults organization="$ORG" project="$PROJECT"
repo_id=$(az repos show --repository "$REPO" --query id --output tsv)
pipeline_id=$(az pipelines show --name "$PR_PIPELINE" --query id --output tsv)
common=(--blocking true --enabled true --branch "$BRANCH" --repository-id "$repo_id")

# One approver who is not the author; new pushes reset votes.
az repos policy approver-count create "${common[@]}" \
  --minimum-approver-count 1 --creator-vote-counts false --allow-downvotes false --reset-on-source-push true

# Every comment must be resolved.
az repos policy comment-required create "${common[@]}"

# Squash merge only.
az repos policy merge-strategy create "${common[@]}" \
  --allow-squash true --allow-no-fast-forward false --allow-rebase false --allow-rebase-merge false

# The Lockstep PR pipeline must pass, and re-runs when main moves.
az repos policy build create "${common[@]}" \
  --build-definition-id "$pipeline_id" --display-name "Lockstep PR checks" \
  --manual-queue-only false --queue-on-source-update-only false --valid-duration 720

# Changes to tests, evals, agent config and pipelines need a required reviewer.
az repos policy required-reviewer create "${common[@]}" \
  --required-reviewer-ids "$TEST_REVIEWERS" \
  --path-filter "/tests/*;*.unit_tests.yml;/evals/*;/.claude/*;/.lockstep/*;/AGENTS.md;/azure-pipelines*" \
  --message "Lockstep: tests, evals, agent config and pipelines need a test reviewer"

echo "Done. Add GitHub Copilot as an automatic reviewer by hand: see docs/branch-policy.md."
