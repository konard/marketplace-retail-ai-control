"""Bitrix24 through an inbound webhook.

REST references (https://apidocs.bitrix24.ru/):

- ``tasks.task.add``, ``tasks.task.get`` - create and read a task;
- ``task.checklistitem.add`` - one checklist item per action;
- ``task.commentitem.add`` - the follow-up result as a task comment;
- ``im.message.add`` - the morning digest in a chat (BB codes);
- the ``OnTaskUpdate`` event tells the system that a task changed.
"""

from __future__ import annotations

from typing import Any

import httpx

from retail_ai_control.connectors import post_json

COMPLETED = "5"


class Bitrix24Client:
    """Calls REST methods as ``POST {webhook}/{method}.json``."""

    def __init__(self, http: httpx.Client, webhook_url: str) -> None:
        self.http = http
        self.webhook_url = webhook_url.rstrip("/")

    def call(self, method: str, params: dict[str, Any]) -> Any:
        """Call a method and return its ``result``."""
        response = post_json(self.http, f"{self.webhook_url}/{method}.json", params)
        return response.json().get("result")

    def add_task(self, fields: dict[str, Any]) -> str:
        """Create a task and return its ID."""
        result = self.call("tasks.task.add", {"fields": fields})
        return str(result["task"]["id"])

    def add_checklist_item(self, task_id: str, title: str) -> None:
        """Add one checklist item to a task."""
        self.call(
            "task.checklistitem.add", {"TASKID": task_id, "FIELDS": {"TITLE": title}}
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Return the task fields (``status``, ``closedDate``, ...)."""
        task: dict[str, Any] = self.call("tasks.task.get", {"taskId": task_id})["task"]
        return task

    def comment(self, task_id: str, text: str) -> None:
        """Add a comment to a task."""
        self.call(
            "task.commentitem.add",
            {"TASKID": task_id, "FIELDS": {"POST_MESSAGE": text}},
        )

    def message(self, dialog_id: str, text: str) -> None:
        """Post a message to a chat."""
        self.call("im.message.add", {"DIALOG_ID": dialog_id, "MESSAGE": text})
