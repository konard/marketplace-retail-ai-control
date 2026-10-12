"""Render every page of the web app on the demo data and print the text."""

from __future__ import annotations

import sys
from datetime import date

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from retail_ai_control.config import Config, Person
from retail_ai_control.demo import load_demo
from retail_ai_control.pilot import Pilot
from retail_ai_control.web import create_app

config = Config(
    database_url="sqlite://",
    margin_plan_pct={"SKU-1001:ozon": 15.0},
    approvers=[1, 7],
    channel_managers={
        "ozon": Person(17, "Анна Смирнова"),
        "wb": Person(18, "Олег Петров"),
    },
)
pilot = Pilot(config, today=lambda: date(2026, 10, 12))
print("deviations:", load_demo(pilot))
client = TestClient(
    create_app(pilot), headers={"X-User-Id": sys.argv[1] if len(sys.argv) > 1 else "1"}
)
for path in [
    "/",
    "/deviations/1",
    "/deviations/2",
    "/evidence/1",
    "/deviations/3",
    "/decisions",
    "/team",
    "/scorecard",
]:
    response = client.get(path)
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    print(f"=== {path} {response.status_code}\n{text[:1500]}\n")
response = client.post("/decisions/1/reject", data={"reason": ""})
print("reject empty:", response.status_code, "Укажите причину" in response.text)
response = client.post("/decisions/1/approve", data={"value_change_price": "abc"})
print("approve abc:", response.status_code, "Введите число" in response.text)
response = client.post("/decisions/1/approve", data={"value_change_price": "20"})
print(
    "approve 20:",
    response.status_code,
    BeautifulSoup(response.text, "html.parser").select_one(".field-error"),
)
response = client.post(
    "/decisions/1/approve",
    data={"value_change_price": "5.0", "value_set_ad_share": "9.0"},
    follow_redirects=False,
)
print("approve ok:", response.status_code, response.headers.get("location"))
print(
    BeautifulSoup(client.get("/deviations/1").text, "html.parser").get_text(
        " ", strip=True
    )[-600:]
)
