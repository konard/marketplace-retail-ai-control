"""Steps of ``features/14_user_interface.feature``.

The checks read the HTML the way assistive technology does: headings,
labels, ``aria-*`` references and text, not classes or colours.
"""

from __future__ import annotations

import re

from bs4 import Tag
from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.support import (
    World,
    labelled_field,
    load_sales,
    number,
    page,
    plain,
    records,
)

scenarios("14_user_interface.feature")

CONCEPT_SALES = [
    ["from", "to", "sku", "channel", "units", "revenue", "commission", "logistics", "advertising"],
    ["2026-10-02", "2026-10-08", "SKU-1001", "ozon", "50", "44000.00", "6600.00", "4400.00", "3960.00"],
    ["2026-10-09", "2026-10-11", "SKU-1001", "ozon", "50", "44000.00", "6600.00", "4400.00", "9240.00"],
    ["2026-10-02", "2026-10-11", "SKU-1001", "wb", "50", "50000.00", "7500.00", "5000.00", "0.00"],
]  # fmt: skip
PAGES = {
    "home page": "/",
    "decision journal": "/decisions",
    "team page": "/team",
    "scorecard page": "/scorecard",
}
QUOTED = re.compile(r'"([^"]+)"')
FIELDS = "input:not([type=hidden]):not([type=submit]), textarea, select"


@given("the deviation from the concept's example has a proposal")
def concept_proposal(world: World) -> None:
    world.config.margin_plan_pct["SKU-1001:ozon"] = 15.0
    with world.pilot.engine.begin() as conn:
        from retail_ai_control.mart import put_cost  # noqa: PLC0415

        put_cost(conn, "SKU-1001", world.today.replace(month=9, day=1), 440.0)
        load_sales(conn, records(CONCEPT_SALES))
    world.pilot.run_rules()
    world.pilot.analyse_open()


@when(
    parsers.re(
        r"user (?P<user>\d+) opens the"
        r" (?P<name>home page|decision card|decision journal|team page|scorecard page)"
    )
)
def opens(world: World, user: str, name: str) -> None:
    url = PAGES.get(name) or f"/deviations/{world.current_deviation()}"
    world.get(url, int(user))
    assert world.response is not None
    assert world.response.status_code == 200


@when(parsers.parse("user {user:d} follows the evidence link of the cause"))
def follows_evidence(world: World, user: int) -> None:
    link = page(world).select_one("a#cause-evidence")
    assert link is not None, "the cause has no evidence link"
    world.get(str(link["href"]), user)


@when(
    parsers.parse("user {user:d} rejects the proposal in the web app without a reason")
)
def rejects_without_reason(world: World, user: int) -> None:
    world.post(f"/decisions/{world.current_decision()}/reject", user, {"reason": ""})


@then(parsers.parse('the page title is "{title}"'))
def page_title(world: World, title: str) -> None:
    assert [plain(item) for item in page(world).select("h1")] == [title]
    head = page(world).title
    assert head is not None
    assert title in plain(head)


@then(parsers.re(r"the first row shows (?P<values>.+)"))
def first_row(world: World, values: str) -> None:
    row = page(world).select_one("tbody tr")
    assert row is not None, "the table is empty"
    cells = [plain(cell) for cell in row.find_all(["th", "td"])]
    for value in QUOTED.findall(values):
        assert value in cells, (value, cells)


@then("the row links to the decision card")
def row_links(world: World) -> None:
    link = page(world).select_one("tbody tr th[scope=row] a[href]")
    assert link is not None
    assert link["href"] == f"/deviations/{world.current_deviation()}"


@then("the card sections are in this order:")
def sections(world: World, datatable: list[list[str]]) -> None:
    found = [plain(item) for item in page(world).select("main h2")]
    assert found == [row["section"] for row in records(datatable)]


@then(parsers.parse('the region "{name}" holds the sections "{names}"'))
def region_sections(world: World, name: str, names: str) -> None:
    names_of = {plain(label): label["id"] for label in page(world).select("main [id]")}
    region = page(world).select_one(
        f'main section[aria-labelledby="{names_of.get(name)}"]'
    )
    assert region is not None, f"no region {name!r}"
    assert [plain(item) for item in region.select("h2")] == names.split(", ")


def rejection(world: World) -> Tag:
    """The disclosure that holds the rejection reason."""
    field = labelled_field(world, "Причина отклонения")
    details = field.find_parent("details")
    assert isinstance(details, Tag), "the reason is not behind a disclosure"
    return details


@then(
    parsers.parse('the rejection reason is hidden behind "{label}" until it is needed')
)
def reason_hidden(world: World, label: str) -> None:
    details = rejection(world)
    summary = details.find("summary")
    assert isinstance(summary, Tag)
    assert plain(summary) == label
    assert not details.has_attr("open")


@then("the rejection reason is open")
def reason_open(world: World) -> None:
    assert rejection(world).has_attr("open")


@then("the card shows a sparkline of the margin rate with a text alternative")
def sparkline(world: World) -> None:
    chart = page(world).select_one("svg.sparkline[role=img]")
    assert chart is not None, "no sparkline"
    caption = page(world).find(id=chart["aria-labelledby"])
    assert isinstance(caption, Tag)
    assert "Маржа" in plain(caption)


@then("the evidence page shows the SQL query and its result rows")
def evidence_page(world: World) -> None:
    query = page(world).select_one("pre code")
    assert query is not None
    assert plain(query).upper().startswith(("SELECT", "WITH"))
    assert page(world).select("tbody tr")


@then(parsers.parse('the explanation is labelled "{label}"'))
def explanation_label(world: World, label: str) -> None:
    assert [plain(item) for item in page(world).select("span.source-label")] == [label]


@then(parsers.parse('the card states "{text}"'))
def card_states(world: World, text: str) -> None:
    assert text in plain(page(world))


@then(parsers.parse('the field "{label}" has the value "{value}"'))
def field_value(world: World, label: str, value: str) -> None:
    field = labelled_field(world, label)
    assert number(str(field["value"])) == number(value)
    assert field["value"] == value


@then(parsers.re(r'the button "(?P<name>[^"]+)" is (?P<negation>not )?available'))
def button(world: World, name: str, negation: str | None) -> None:
    found = [item for item in page(world).select("button") if plain(item) == name]
    assert bool(found) is (negation is None)


@then(parsers.parse('the page language is "{lang}"'))
def language(world: World, lang: str) -> None:
    html = page(world).find("html")
    assert isinstance(html, Tag)
    assert html.get("lang") == lang


@then("every form field has a label")
def labels(world: World) -> None:
    targets = {str(item["for"]) for item in page(world).select("label[for]")}
    for field in page(world).select(FIELDS):
        assert field.get("id") in targets or field.get("aria-label"), field


@then("every status is shown as text, not only by colour")
def statuses(world: World) -> None:
    for item in page(world).select(".status"):
        assert plain(item), item


@then("the page has one main landmark and one level-one heading")
def landmarks(world: World) -> None:
    assert len(page(world).select("main")) == 1
    assert len(page(world).select("h1")) == 1
