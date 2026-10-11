"""The AI agent: explains deviations and answers questions with SQL tools.

Any OpenAI-compatible chat completions endpoint works (see
:class:`~retail_ai_control.config.LLMSettings`). The model calls tools that
return query results; the final answer is JSON. Two guards make the output
safe to show:

- every number in the text must appear in the evidence or the settings;
- every action must have a known type and stay within the limits.

If the model is unavailable or the answer fails a guard, the rule-based
result stays and the reason is written to the analysis log.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, cast

import openai

from retail_ai_control import queries
from retail_ai_control.config import Config

if TYPE_CHECKING:
    from retail_ai_control.analysis import Analysis
    from retail_ai_control.pilot import Pilot

logger = logging.getLogger(__name__)
NUMBER = re.compile(r"(?<![\w-])[-−+]?\d+(?:[.,]\d+)?")
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
UNAVAILABLE = "AI-ассистент сейчас недоступен. Данные — в дашборде."
UNSUPPORTED = "Не удалось подтвердить цифры ответа данными. Проверьте дашборд."
EXPLAIN_PROMPT = """Ты аналитик продаж на Wildberries и Ozon. Объясни отклонение \
руководителю в 1-2 предложениях по-русски и предложи действия.
Правила:
- цифры бери только из результатов инструментов, проценты пиши как 4,0%;
- действия только из списка: set_ad_share (доля рекламы, % выручки), \
change_price (изменение цены, %), restock (поставка, шт.), review (проверка);
- соблюдай лимиты из сообщения пользователя;
- ответ - только JSON: {"explanation": "...", "actions": [{"type": "...", "value": 0}]}."""
QUESTION_PROMPT = """Ты аналитик продаж на Wildberries и Ozon. Ответь собственнику \
кратко по-русски. Цифры бери только из результатов инструментов, проценты пиши \
как 4,0%. Ответ - только JSON: {"answer": "..."}."""
Tool = Callable[[dict[str, Any]], Any]


def _schema(name: str, description: str, sql: bool = False) -> dict[str, Any]:
    properties = (
        {"sql": {"type": "string", "description": "Один SELECT к витрине"}}
        if sql
        else {}
    )
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
            },
        },
    }


RUN_SQL = _schema(
    "run_sql",
    "Выполнить один SELECT (только чтение). Таблицы: unit_economics(channel, sku, day, "
    "units, revenue, commission, logistics, advertising, cogs, margin), stock_daily, product.",
    sql=True,
)


def parse_number(text: str) -> float:
    """Read ``−7,5`` or ``+5.0`` as a float."""
    return float(text.replace("−", "-").replace(",", ".").lstrip("+"))


def unsupported_figures(text: str, allowed: set[float]) -> list[str]:
    """Return the numbers in ``text`` that are not in ``allowed``."""
    return [
        match.lstrip("+-−")
        for match in NUMBER.findall(text)
        if round(abs(parse_number(match)), 1) not in allowed
    ]


def config_numbers(config: Config) -> set[float]:
    """Numbers from the settings that a text may cite (periods, limits)."""
    values = [
        config.margin_days,
        config.baseline_days,
        config.followup_days,
        config.min_cover_days,
        config.ad_share_limit_pct,
        config.sales_drop_pct,
        config.price_change_max_pct,
        config.price_step_pct,
        config.target_gap_pp,
        config.guardrail_drop_pct,
        config.reconciliation_tolerance_pct,
        *config.margin_plan_pct.values(),
    ]
    return {round(float(value), 1) for value in values}


def action_error(action: Any, config: Config) -> Optional[str]:
    """Explain why an action is not allowed, or return ``None``."""
    if not isinstance(action, dict) or "type" not in action:
        return f"malformed action {action!r}"
    kind, value = action["type"], action.get("value")
    if kind == "review":
        return None
    if kind not in ("set_ad_share", "change_price", "restock") or not isinstance(
        value, (int, float)
    ):
        return f"unknown action {kind} {value!r}"
    if kind == "change_price" and abs(value) > config.price_change_max_pct:
        return f"change_price {float(value):.1f} exceeds limit {config.price_change_max_pct:.1f}"
    if kind == "set_ad_share" and not 0 <= value <= config.ad_share_limit_pct:
        return f"set_ad_share {float(value):.1f} exceeds limit {config.ad_share_limit_pct:.1f}"
    if kind == "restock" and value < 0:
        return f"restock {value} is negative"
    return None


def parse_answer(content: str) -> dict[str, Any]:
    """Read the JSON answer; tolerate a Markdown code fence around it."""
    data = json.loads(FENCE.sub("", content.strip()))
    if not isinstance(data, dict):
        msg = "the answer is not a JSON object"
        raise TypeError(msg)
    return data


@dataclass
class Answer:
    """The answer to a question and the links to check it."""

    text: str
    links: list[tuple[str, str]] = field(default_factory=list)
    label: str = "Сгенерировано AI"


class Agent:
    """A chat-completions tool loop bound to the data mart."""

    def __init__(self, pilot: Pilot) -> None:
        settings = pilot.config.llm
        self.pilot = pilot
        self.settings = settings
        self.client = openai.OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key or "not-needed",
            project=settings.project or None,
            max_retries=0,
            # The SDK accepts any httpx-compatible client; tests pass a mock.
            http_client=cast(Any, pilot.http),
        )

    def _chat(
        self,
        system: str,
        user: str,
        tools: dict[str, Tool],
        schemas: list[dict[str, Any]],
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for step in range(self.settings.max_tool_calls + 1):
            last = step == self.settings.max_tool_calls
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=cast(Any, messages),
                tools=cast(Any, schemas),
                tool_choice="none" if last else "auto",
                temperature=0,
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                return message.content or ""
            messages.append(message.model_dump(exclude_none=True))
            for call in calls:
                function = getattr(call, "function", None)
                name = function.name if function else ""
                try:
                    arguments = (
                        json.loads(function.arguments or "{}") if function else {}
                    )
                    result = (
                        tools[name](arguments)
                        if name in tools
                        else {"error": f"unknown tool {name}"}
                    )
                except (ValueError, KeyError, TypeError) as error:
                    result = {"error": str(error)}
                logger.info("tool %s called", name)
                content = json.dumps(result, ensure_ascii=False, default=str)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": content}
                )
        msg = "the model did not answer after the tool calls"
        raise ValueError(msg)

    def _run_sql(self, found: dict[str, queries.Evidence]) -> Tool:
        def run_sql(arguments: dict[str, Any]) -> Any:
            try:
                item = queries.run_readonly_sql(
                    self.pilot.engine, str(arguments.get("sql", ""))
                )
            except queries.QueryRefusedError as error:
                return {"error": str(error)}
            found[f"run_sql_{len(found) + 1}"] = item
            return {"rows": item.rows}

        return run_sql

    def explain(self, analysis: Analysis) -> None:
        """Replace the rule-based explanation if the AI answer passes the guards."""
        from retail_ai_control.analysis import AI_LABEL  # noqa: PLC0415 - cycle

        config = self.pilot.config
        dev = analysis.deviation

        def evidence_tool(name: str) -> Tool:
            return lambda _arguments: {
                "sql": analysis.evidence[name].sql,
                "rows": analysis.evidence[name].rows,
            }

        tools = {name: evidence_tool(name) for name in analysis.evidence}
        tools["run_sql"] = self._run_sql(analysis.evidence)
        schemas = [
            _schema(name, f"Результат запроса {name} по отклонению")
            for name in analysis.evidence
        ]
        user = (
            f"Отклонение: {dev['rule']}, {dev['sku']} на {dev['channel']}, {dev['message']}. "
            f"Период: {analysis.now_from} - {analysis.now_to}. Цель по марже: {analysis.target_pct}%. "
            f"Лимиты: изменение цены до {config.price_change_max_pct}%, "
            f"доля рекламы до {config.ad_share_limit_pct}%. "
            f"Расчёт по правилам: {analysis.explanation} Действия: {json.dumps(analysis.actions)}"
        )
        try:
            data = parse_answer(
                self._chat(EXPLAIN_PROMPT, user, tools, [*schemas, RUN_SQL])
            )
            explanation = str(data["explanation"]).strip()
            actions = data.get("actions") or []
        except openai.APIError as error:
            self._reject(analysis, f"AI unavailable: {error}")
            return
        except (ValueError, KeyError, TypeError) as error:
            self._reject(analysis, f"AI answer rejected: invalid answer {error}")
            return
        allowed = analysis.numbers() | config_numbers(config)
        unsupported = unsupported_figures(explanation, allowed)
        errors = [f"unsupported figure {figure}" for figure in unsupported]
        errors += [
            error
            for error in (action_error(action, config) for action in actions)
            if error
        ]
        if errors or not explanation:
            self._reject(
                analysis,
                "AI answer rejected: " + "; ".join(errors or ["empty explanation"]),
            )
            return
        analysis.explanation = explanation
        if actions:
            analysis.actions = [
                {"type": item["type"], "value": item.get("value")} for item in actions
            ]
        analysis.label = AI_LABEL
        analysis.log.append("AI explanation accepted")

    def _reject(self, analysis: Analysis, reason: str) -> None:
        analysis.log.append(reason)
        self.pilot.note(reason)

    def answer(self, question: str) -> Answer:
        """Answer a question about the business; the figures are checked."""
        config = self.pilot.config
        today = self.pilot.today()
        now_to = today - timedelta(1)
        now_from = now_to - timedelta(config.margin_days - 1)
        before_from = now_from - timedelta(config.baseline_days)
        found: dict[str, queries.Evidence] = {}

        def margin_by_channel(_arguments: dict[str, Any]) -> Any:
            with self.pilot.engine.connect() as conn:
                item = queries.run(
                    conn,
                    "margin_by_channel",
                    before_from=before_from,
                    now_from=now_from,
                    now_to=now_to,
                )
            found["margin_by_channel"] = item
            return {"sql": item.sql, "params": item.params, "rows": item.rows}

        tools = {
            "margin_by_channel": margin_by_channel,
            "run_sql": self._run_sql(found),
        }
        schemas = [
            _schema(
                "margin_by_channel",
                f"Маржа и доля рекламы по каналам: последние {config.margin_days} дн. (now) "
                f"и {config.baseline_days} дн. до них (before)",
            ),
            RUN_SQL,
        ]
        dashboard = [("Дашборд", config.dashboard_url or config.web_url)]
        try:
            text = str(
                parse_answer(self._chat(QUESTION_PROMPT, question, tools, schemas))[
                    "answer"
                ]
            ).strip()
        except openai.APIError as error:
            self.pilot.note(f"AI unavailable: {error}")
            return Answer(UNAVAILABLE, dashboard, "")
        except (ValueError, KeyError, TypeError) as error:
            self.pilot.note(f"AI answer rejected: invalid answer {error}")
            return Answer(UNSUPPORTED, dashboard, "")
        allowed = config_numbers(config).union(
            *(item.numbers() for item in found.values())
        )
        unsupported = unsupported_figures(text, allowed)
        if unsupported or not text:
            self.pilot.note(
                f"AI answer rejected: unsupported figure {', '.join(unsupported)}"
            )
            return Answer(UNSUPPORTED, dashboard, "")
        links = []
        with self.pilot.engine.begin() as conn:
            for name, item in found.items():
                queries.save(conn, item, None)
                links.append((name, f"/evidence/{item.id}"))
        return Answer(text, links)
