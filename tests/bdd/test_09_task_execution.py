"""Steps of ``features/09_task_execution.feature``."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.support import APPLICATION_TOKEN, World, day, records

scenarios("09_task_execution.feature")


@given(parsers.parse('Bitrix24 answers 503 to the next "{method}" call'))
def bitrix_down(world: World, method: str) -> None:
    world.net.bitrix_fail[method] = 1


@given(
    parsers.re(
        r'the Bitrix24 task has status (?P<status>\d+) "[^"]+"'
        r"(?: closed on (?P<closed>\S+))?"
    )
)
def task_status(world: World, status: str, closed: str | None) -> None:
    task = world.net.tasks[world.decision_row()["task_id"]]
    task["status"] = status
    if closed:
        task["closedDate"] = f"{closed}T18:00:00+03:00"


@when("the pending tasks are retried")
def retried(world: World) -> None:
    world.pilot.retry_tasks()


@when(
    parsers.re(
        r'Bitrix24 sends the "(?P<event>\w+)" event for the task'
        r" with (?P<token>the correct|a wrong) application token"
    )
)
def task_event(world: World, event: str, token: str) -> None:
    world.response = world.client.post(
        "/webhooks/bitrix24",
        data={
            "event": event,
            "data[FIELDS_AFTER][ID]": world.decision_row()["task_id"],
            "auth[application_token]": (
                APPLICATION_TOKEN if token == "the correct" else "wrong"
            ),
        },
    )


@then(parsers.parse('the task description contains "{text}"'))
def description(world: World, text: str) -> None:
    assert text in world.net.calls("tasks.task.add")[-1]["fields"]["DESCRIPTION"]


@then(parsers.parse('Bitrix24 receives "{method}" for each action:'))
def for_each_action(world: World, method: str, datatable: list[list[str]]) -> None:
    task_id = world.decision_row()["task_id"]
    calls = world.net.calls(method)
    assert [call["TASKID"] for call in calls] == [task_id] * len(calls)
    assert [call["FIELDS"]["TITLE"] for call in calls] == [
        row["title"] for row in records(datatable)
    ]


@then(parsers.parse('the task deadline is "{deadline}"'))
def task_deadline(world: World, deadline: str) -> None:
    assert world.net.calls("tasks.task.add")[-1]["fields"]["DEADLINE"] == deadline


@then(parsers.parse("Bitrix24 created exactly {count:d} task"))
def created(world: World, count: int) -> None:
    assert len(world.net.calls("tasks.task.add")) == count


@then(parsers.parse("the event endpoint answers {status:d}"))
def event_answer(world: World, status: int) -> None:
    assert world.response is not None
    assert world.response.status_code == status


@then(parsers.parse("the change date is {on_day}"))
def change_date(world: World, on_day: str) -> None:
    assert world.decision_row()["completed_on"] == day(on_day)


@then(parsers.parse("the follow-up is due on {on_day}"))
def followup_due(world: World, on_day: str) -> None:
    assert world.decision_row()["followup_due"] == day(on_day)
