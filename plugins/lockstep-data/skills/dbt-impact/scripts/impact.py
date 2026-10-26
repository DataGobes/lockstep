#!/usr/bin/env python3
"""Show what a dbt change affects, from two manifests: the branch's and the last prod deploy's.

  dbt parse                                     # writes target/manifest.json for the branch
  python3 impact.py --manifest target/manifest.json --state prod-state/manifest.json

Prints Markdown: the models, seeds and snapshots that changed (body, config or contract) or were removed, everything
downstream of them in dbt (models, exposures), which changed models have an enforced contract (a change there needs a
new model version), the Unity Catalog lineage query that finds consumers outside dbt (Genie spaces, dashboards, jobs,
notebooks), and a dbt-audit-helper call per changed model for the data diff. Reads the manifests only; it runs no
dbt and queries nothing. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

KINDS = ("model", "seed", "snapshot")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"impact: {path} not found (run `dbt parse`, or download the dbt-prod-state artifact)"
        ) from None


def _fingerprint(node: dict) -> tuple:
    config = {k: v for k, v in node.get("config", {}).items() if k not in ("meta", "tags", "docs")}
    columns = {name: col.get("data_type") for name, col in node.get("columns", {}).items()}
    return (
        node.get("checksum", {}).get("checksum"),
        json.dumps(config, sort_keys=True),
        json.dumps(columns, sort_keys=True),
    )


def _nodes(manifest: dict) -> dict[str, dict]:
    return {uid: n for uid, n in manifest.get("nodes", {}).items() if n.get("resource_type") in KINDS}


def changed(current: dict, prod: dict) -> tuple[list[str], list[str]]:
    now, before = _nodes(current), _nodes(prod)
    modified = sorted(
        uid for uid, n in now.items() if uid not in before or _fingerprint(n) != _fingerprint(before[uid])
    )
    removed = sorted(set(before) - set(now))
    return modified, removed


def downstream(current: dict, start: list[str]) -> list[str]:
    children = current.get("child_map", {})
    seen, queue = set(start), deque(start)
    while queue:
        for child in children.get(queue.popleft(), []):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return sorted(seen - set(start))


def contracted(current: dict, uids: list[str]) -> list[str]:
    nodes = current.get("nodes", {})
    return [u for u in uids if nodes.get(u, {}).get("config", {}).get("contract", {}).get("enforced")]


def _name(uid: str) -> str:
    return uid.split(".", 2)[-1]


def _relation(manifest: dict, uid: str) -> str | None:
    node = manifest.get("nodes", {}).get(uid) or {}
    rel = node.get("relation_name")
    return rel.replace("`", "") if rel else None


def lineage_sql(tables: list[str]) -> str:
    listed = ",\n    ".join(f"'{t}'" for t in tables)
    return (
        "-- Consumers of the changed tables outside dbt, last 90 days. Run as yourself on a SQL warehouse.\n"
        "SELECT DISTINCT source_table_full_name, target_table_full_name, entity_type, entity_id\n"
        "FROM system.access.table_lineage\n"
        f"WHERE source_table_full_name IN (\n    {listed}\n)\n"
        "  AND event_date >= current_date() - INTERVAL 90 DAYS\n"
        "ORDER BY source_table_full_name, entity_type"
    )


def audit_call(prod: dict, uid: str) -> str | None:
    node = prod.get("nodes", {}).get(uid)
    if not node:
        return None
    return (
        "{{ audit_helper.compare_all_columns(\n"
        f"    a_relation=api.Relation.create(database='{node.get('database')}', schema='{node.get('schema')}', "
        f"identifier='{node.get('alias') or node.get('name')}'),\n"
        f"    b_relation=ref('{node.get('name')}'),\n"
        "    primary_key='<primary key column>'\n) }}"
    )


def report(current: dict, prod: dict) -> str:
    modified, removed = changed(current, prod)
    down = downstream(current, modified)
    out = ["## Changed", ""] + ([f"- `{_name(u)}`" for u in modified] or ["- none"])
    if removed:
        out += ["", "## Removed (anything that reads them breaks)", ""] + [f"- `{_name(u)}`" for u in removed]
    out += ["", "## Downstream in dbt", ""] + ([f"- `{_name(u)}`" for u in down] or ["- none"])
    enforced = contracted(current, modified)
    out += ["", "## Enforced contracts changed (need a new model version)", ""]
    out += [f"- `{_name(u)}`" for u in enforced] or ["- none"]
    tables = [t for t in (_relation(prod, u) for u in [*modified, *removed]) if t]
    if tables:
        out += ["", "## Consumers outside dbt", "", "```sql", lineage_sql(tables), "```"]
    calls = [(u, audit_call(prod, u)) for u in modified if u.startswith("model.")]
    calls = [(u, c) for u, c in calls if c]  # new models have nothing in prod to compare with
    if calls:
        out += ["", "## Data diff (dbt-audit-helper, in an analysis or `dbt compile --inline`)", ""]
        for uid, call in calls:
            out += [f"`{_name(uid)}`:", "", "```sql", call, "```", ""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=Path("target/manifest.json"), help="the branch's manifest")
    ap.add_argument("--state", type=Path, default=Path("prod-state/manifest.json"), help="the prod manifest")
    args = ap.parse_args(argv)
    print(report(load(args.manifest), load(args.state)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
