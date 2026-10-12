"""Steps of ``features/06_questions.feature``."""

from __future__ import annotations

from pytest_bdd import parsers, scenarios, then, when

from tests.bdd.support import World

scenarios("06_questions.feature")

OWNER = 1


@when(parsers.parse('the owner asks "{question}"'))
def owner_asks(world: World, question: str) -> None:
    world.found["answer"] = world.pilot.ask(question)


@when("the owner sends an empty question in the web app")
def empty_question(world: World) -> None:
    world.post("/ask", OWNER, {"question": " "})


@then(parsers.parse('the answer is "{text}"'))
def answer_is(world: World, text: str) -> None:
    assert world.found["answer"].text == text


@then(parsers.parse('the answer links to the evidence of the query "{name}"'))
def evidence_link(world: World, name: str) -> None:
    links = dict(world.found["answer"].links)
    assert links[name].startswith("/evidence/")
    page = world.get(links[name], 1)
    assert world.response is not None
    assert world.response.status_code == 200
    assert page.select_one("pre code") is not None


@then("the answer links to the dashboard")
def dashboard_link(world: World) -> None:
    assert world.found["answer"].links == [("Дашборд", world.config.web_url)]
