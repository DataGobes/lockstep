# dbt-impact

**What it does.** From the branch and prod manifests, lists the changed models, everything downstream of them,
enforced contracts that need a new model version, the Unity Catalog lineage query for consumers outside dbt, and a
data diff call per model.

**When to reach for it.** Before opening a PR that changes dbt models, or when a spec asks who is affected.

**Common questions.**
- *Why is a model "changed" when I only edited its docs?* It isn't: descriptions, tags and meta are ignored.
- *Why doesn't it run the lineage query?* Querying data is for a person with the right access, not the agent.

**It's working if** no consumer is surprised by a change, and contract changes always arrive as new versions.
