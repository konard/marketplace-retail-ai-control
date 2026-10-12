"""Steps of ``features/08_decision_approval.feature``."""

from __future__ import annotations

from pytest_bdd import parsers, scenarios, then, when

from tests.bdd.conftest import journal_of
from tests.bdd.support import World, text_of

scenarios("08_decision_approval.feature")


@when(
    parsers.parse("user {user:d} approves the proposal with the price change {value}")
)
def approves_edited(world: World, user: int, value: str) -> None:
    form = {"value_change_price": value.removesuffix("%")}
    world.post(f"/decisions/{world.current_decision()}/approve", user, form)


@when(
    parsers.parse('user {user:d} approves the proposal without the action "{action}"')
)
def approves_without(world: World, user: int, action: str) -> None:
    form = {f"value_{action.replace(' ', '_')}": ""}
    world.post(f"/decisions/{world.current_decision()}/approve", user, form)


@when(parsers.parse("user {user:d} rejects the proposal without a reason"))
def rejects_without_reason(world: World, user: int) -> None:
    world.post(f"/decisions/{world.current_decision()}/reject", user, {"reason": ""})


@when(parsers.parse('user {user:d} rejects the proposal with the reason "{reason}"'))
def rejects(world: World, user: int, reason: str) -> None:
    world.post(
        f"/decisions/{world.current_decision()}/reject", user, {"reason": reason}
    )


@then(parsers.parse('the decision journal records "{stage}" by user {user:d}'))
def journal_by(world: World, stage: str, user: int) -> None:
    assert [
        event["user_id"] for event in journal_of(world) if event["stage"] == stage
    ] == [user]


@then(
    parsers.parse(
        'the decision journal records "{stage}" by user {user:d} with "{note}"'
    )
)
def journal_with(world: World, stage: str, user: int, note: str) -> None:
    events = [event for event in journal_of(world) if event["stage"] == stage]
    assert [(event["user_id"], event["note"]) for event in events] == [(user, note)]


@then(parsers.parse('the decision journal records "{stage}" exactly once'))
def journal_once(world: World, stage: str) -> None:
    assert [event["stage"] for event in journal_of(world)].count(stage) == 1


@then(parsers.parse("the request is refused with status {status:d}"))
def refused_status(world: World, status: int) -> None:
    assert world.response is not None
    assert world.response.status_code == status


@then(parsers.parse('the request is refused with the message "{message}"'))
def refused_message(world: World, message: str) -> None:
    assert world.response is not None
    assert world.response.status_code == 422
    assert world.page is not None
    assert message in text_of(world.page)


@then(parsers.re("the edit is (?P<negation>not )?significant"))
def edit_significance(world: World, negation: str | None) -> None:
    assert world.decision_row()["significant_edit"] is (negation is None)


@then(parsers.parse("the decision is approved by user {user:d} today"))
def approved_today(world: World, user: int) -> None:
    row = world.decision_row()
    assert (row["approved_by"], row["decided_on"]) == (user, world.today)
    assert "approved" in [event["stage"] for event in journal_of(world)]
