"""Steps of ``features/05_ai_analysis.feature``."""

from __future__ import annotations

import json

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import func, select

from retail_ai_control.mart import evidence, sales_daily
from tests.bdd.fakes import Reply
from tests.bdd.support import World, actions_of, number, records

scenarios("05_ai_analysis.feature")


@given(parsers.parse("the price change limit is {limit}%"))
def price_limit(world: World, limit: str) -> None:
    world.config.price_change_max_pct = number(limit)


@then(parsers.parse("the cost share changes against the previous {count:d} days are:"))
def share_changes(world: World, count: int, datatable: list[list[str]]) -> None:
    assert world.config.baseline_days == count
    assert world.analysis is not None
    for row in records(datatable):
        before, now = world.analysis.shares[row["item"]]
        assert before is not None
        assert now is not None
        assert round(before, 1) == number(row["before"]), row["item"]
        assert round(now, 1) == number(row["now"]), row["item"]
        assert round(now - before, 1) == number(row["change"]), row["item"]


@then(parsers.parse('the main cause is "{cause}"'))
def main_cause(world: World, cause: str) -> None:
    assert world.analysis is not None
    assert world.analysis.cause == cause


@then(
    parsers.parse(
        'the analysis notes that the unit price on "{channel}" is {gap}% below "{other}"'
    )
)
def price_gap(world: World, channel: str, gap: str, other: str) -> None:
    assert world.analysis is not None
    assert world.analysis.deviation["channel"] == channel
    assert world.analysis.other_channel == other
    assert world.analysis.price_gap_pct == number(gap)


@then("the proposal contains the actions:")
def proposal_actions(world: World, datatable: list[list[str]]) -> None:
    assert world.decision_row()["actions"] == actions_of(datatable)


@then(parsers.parse("the target is a margin rate of at least {target}%"))
def target(world: World, target: str) -> None:
    assert world.decision_row()["target_pct"] == number(target)


@then(parsers.parse("the guardrail is a sales drop of at most {guardrail}%"))
def guardrail(world: World, guardrail: str) -> None:
    assert world.decision_row()["guardrail_pct"] == number(guardrail)


@then("every figure in the analysis has evidence with a SQL query and its result rows")
def figures_have_evidence(world: World) -> None:
    assert world.analysis is not None
    assert world.analysis.figures
    with world.pilot.engine.connect() as conn:
        for name, figure in world.analysis.figures.items():
            row = (
                conn.execute(
                    select(evidence).where(evidence.c.id == figure["evidence_id"])
                )
                .mappings()
                .one()
            )
            assert row["name"] == figure["evidence"], name
            assert row["sql"].lstrip().upper().startswith(("SELECT", "WITH")), name
            assert row["rows"], name


@then(parsers.parse('the explanation is "{text}"'))
def explanation(world: World, text: str) -> None:
    assert world.analysis is not None
    assert world.analysis.explanation == text
    assert world.decision_row()["explanation"] == text


@then(parsers.parse('the analysis is labelled "{label}"'))
def labelled(world: World, label: str) -> None:
    assert world.analysis is not None
    assert world.analysis.label == label
    assert world.decision_row()["label"] == label


@then(parsers.parse('the AI agent called the tool "{tool}"'))
def tool_called(world: World, tool: str) -> None:
    results = world.net.tool_results(tool)
    assert results, f"the agent did not answer a {tool} call"
    assert "error" not in json.loads(results[-1])


@then(parsers.parse('the analysis log contains "{text}"'))
def log_contains(world: World, text: str) -> None:
    assert world.analysis is not None
    assert any(text in line for line in world.analysis.log), world.analysis.log


@when(parsers.parse('the AI agent runs the SQL "{sql}"'))
def runs_sql(world: World, sql: str) -> None:
    world.enable_ai()
    world.net.llm_replies = [
        Reply(tool="run_sql", arguments={"sql": sql}),
        Reply(content='{"answer": "Готово."}'),
    ]
    world.pilot.ask("Сколько строк продаж?")
    world.found["sql"] = json.loads(world.net.tool_results("run_sql")[-1])


@then("the query is refused")
def refused(world: World) -> None:
    assert "error" in world.found["sql"]
    assert "rows" not in world.found["sql"]


@then(parsers.parse("the data mart still has {count:d} daily sales facts"))
def facts_kept(world: World, count: int) -> None:
    with world.pilot.engine.connect() as conn:
        assert (
            conn.execute(select(func.count()).select_from(sales_daily)).scalar()
            == count
        )


@then(parsers.parse('the query returns the row "{row}"'))
def returns_row(world: World, row: str) -> None:
    name, value = row.split("=")
    assert world.found["sql"]["rows"] == [{name: int(value)}]
