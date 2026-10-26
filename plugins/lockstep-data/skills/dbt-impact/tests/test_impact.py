"""Run with: python3 -m pytest plugins/lockstep-data/skills/dbt-impact/tests (from the Lockstep repo root)."""

import copy
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("impact", HERE.parent / "scripts" / "impact.py")
impact = importlib.util.module_from_spec(spec)
sys.modules["impact"] = impact
spec.loader.exec_module(impact)


def node(name, checksum="a", contract=False, kind="model"):
    return {
        "resource_type": kind,
        "name": name,
        "database": "dev_cat",
        "schema": "marts",
        "alias": name,
        "relation_name": f"`prod_cat`.`marts`.`{name}`",
        "checksum": {"name": "sha256", "checksum": checksum},
        "config": {"materialized": "table", "contract": {"enforced": contract}},
        "columns": {"id": {"data_type": "bigint"}},
    }


PROD = {
    "nodes": {
        "model.p.stg_orders": node("stg_orders"),
        "model.p.fct_revenue": node("fct_revenue", contract=True),
        "model.p.dim_customer": node("dim_customer"),
        "model.p.old_model": node("old_model"),
    },
    "child_map": {
        "model.p.stg_orders": ["model.p.fct_revenue"],
        "model.p.fct_revenue": ["exposure.p.revenue_dashboard"],
    },
}


def branch(**changes):
    current = copy.deepcopy(PROD)
    del current["nodes"]["model.p.old_model"]
    for uid, edit in changes.items():
        edit(current["nodes"].setdefault(uid, node(uid.split(".")[-1])))
    return current


def test_body_change_flows_downstream_to_models_and_exposures():
    current = branch(**{"model.p.stg_orders": lambda n: n["checksum"].update(checksum="b")})
    modified, removed = impact.changed(current, PROD)
    assert modified == ["model.p.stg_orders"]
    assert removed == ["model.p.old_model"]
    assert impact.downstream(current, modified) == ["exposure.p.revenue_dashboard", "model.p.fct_revenue"]


def test_config_and_column_type_changes_count():
    current = branch(
        **{
            "model.p.dim_customer": lambda n: n["config"].update(materialized="incremental"),
            "model.p.fct_revenue": lambda n: n["columns"]["id"].update(data_type="string"),
        }
    )
    modified, _ = impact.changed(current, PROD)
    assert modified == ["model.p.dim_customer", "model.p.fct_revenue"]
    assert impact.contracted(current, modified) == ["model.p.fct_revenue"]


def test_tags_and_docs_alone_are_not_a_change():
    current = branch(**{"model.p.dim_customer": lambda n: n["config"].update(tags=["finance"])})
    assert impact.changed(current, PROD)[0] == []


def test_report_has_lineage_sql_and_audit_calls():
    current = branch(
        **{
            "model.p.fct_revenue": lambda n: n["checksum"].update(checksum="b"),
            "model.p.new_model": lambda n: None,
        }
    )
    text = impact.report(current, PROD)
    assert "- `fct_revenue`" in text.split("## Enforced contracts")[1]
    assert "'prod_cat.marts.fct_revenue'" in text and "'prod_cat.marts.old_model'" in text
    assert "system.access.table_lineage" in text
    assert "b_relation=ref('fct_revenue')" in text
    assert "ref('new_model')" not in text  # nothing in prod to compare a new model with


def test_no_change():
    current = copy.deepcopy(PROD)
    text = impact.report(current, PROD)
    assert text.startswith("## Changed\n\n- none")
    assert "table_lineage" not in text
