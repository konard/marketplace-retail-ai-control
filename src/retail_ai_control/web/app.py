"""The web app: decision cards, the journal, team and pilot pages, webhooks.

Server-rendered HTML (FastAPI, Jinja2 and Pico CSS) without JavaScript, so
the pages work with a keyboard, a screen reader and any browser. The page
rules are in ``docs/ux/README.md``.

The user comes from the ``X-User-Id`` header, which the company's single
sign-on proxy sets (for example oauth2-proxy with Bitrix24 OAuth). For a
local demo, ``create_app(pilot, default_user=1)`` acts as user 1.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from retail_ai_control.decisions import DecisionError, get
from retail_ai_control.fmt import day, money
from retail_ai_control.web import views

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

HERE = Path(__file__).parent
USER_HEADER = "X-User-Id"
NOT_A_NUMBER = "Введите число, например 5.0"


def _number(text: str) -> float:
    return float(text.strip().replace(",", ".").replace("−", "-"))


def create_app(pilot: Pilot, default_user: Optional[int] = None) -> FastAPI:
    """Build the app around one pilot."""
    app = FastAPI(title="Контур управления", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters.update(money=money, day=day, status_class=views.status_class)

    def user_of(request: Request) -> Optional[int]:
        raw = request.headers.get(USER_HEADER)
        if raw is None:
            return default_user
        try:
            return int(raw)
        except ValueError as error:
            raise HTTPException(400, f"{USER_HEADER} must be a number") from error

    def page(
        request: Request, name: str, status_code: int = 200, **context: Any
    ) -> HTMLResponse:
        context.setdefault("user", user_of(request))
        return templates.TemplateResponse(
            request, name, context, status_code=status_code
        )

    def card_page(
        request: Request,
        deviation_id: int,
        status_code: int = 200,
        errors: Optional[dict[str, str]] = None,
        form: Optional[dict[str, str]] = None,
    ) -> HTMLResponse:
        try:
            card = views.build_card(pilot, deviation_id, user_of(request))
        except LookupError as error:
            raise HTTPException(404, "Отклонение не найдено") from error
        for action in card.actions:
            key = f"value_{action['type']}"
            if form and key in form:
                action["value"] = form[key]
        return page(
            request,
            "card.html.jinja",
            status_code,
            title=f"{card.deviation['sku']} · {card.channel}",
            card=card,
            limits_note=views.LIMITS_NOTE,
            errors=errors or {},
            reason=(form or {}).get("reason", ""),
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return page(
            request,
            "home.html.jinja",
            title="Отклонения и решения",
            nav="home",
            rows=views.home_rows(pilot),
            warnings=views.data_warnings(pilot),
        )

    @app.get("/deviations/{deviation_id}", response_class=HTMLResponse)
    def card(request: Request, deviation_id: int) -> HTMLResponse:
        return card_page(request, deviation_id)

    @app.post("/decisions/{decision_id}/approve", response_model=None)
    async def approve(request: Request, decision_id: int) -> Response:
        form = {key: str(value) for key, value in (await request.form()).items()}
        user = user_of(request)
        row = await run_in_threadpool(_decision, pilot, decision_id)
        actions, errors = [], {}
        for action in row["actions"]:
            key = f"value_{action['type']}"
            if action["type"] not in views.EDITABLE or key not in form:
                actions.append(action)
                continue
            if not form[key].strip():
                continue  # an empty field removes the action
            try:
                actions.append({"type": action["type"], "value": _number(form[key])})
            except ValueError:
                errors[key] = NOT_A_NUMBER
        if not errors:
            try:
                await run_in_threadpool(pilot.approve, decision_id, user or 0, actions)
                return RedirectResponse(
                    f"/deviations/{row['deviation_id']}", status_code=303
                )
            except DecisionError as error:
                key = f"value_{error.field}" if error.field else "decision"
                errors[key] = error.message
                status = error.status
        else:
            status = 422
        return card_page(request, row["deviation_id"], status, errors, form)

    @app.post("/decisions/{decision_id}/reject", response_model=None)
    def reject(request: Request, decision_id: int, reason: str = Form("")) -> Response:
        row = _decision(pilot, decision_id)
        try:
            pilot.reject(decision_id, user_of(request) or 0, reason)
        except DecisionError as error:
            key = error.field or "decision"
            return card_page(
                request,
                row["deviation_id"],
                error.status,
                {key: error.message},
                {"reason": reason},
            )
        return RedirectResponse(f"/deviations/{row['deviation_id']}", status_code=303)

    @app.get("/evidence/{evidence_id}", response_class=HTMLResponse)
    def evidence(request: Request, evidence_id: int) -> HTMLResponse:
        try:
            item = views.evidence_page(pilot, evidence_id)
        except LookupError as error:
            raise HTTPException(404, "Данные не найдены") from error
        return page(
            request,
            "evidence.html.jinja",
            title=f"Данные: {item['name']}",
            item=item,
        )

    @app.get("/team", response_class=HTMLResponse)
    def team(request: Request) -> HTMLResponse:
        return page(
            request, "team.html.jinja", title="Команда", nav="team", rows=pilot.team()
        )

    @app.get("/scorecard", response_class=HTMLResponse)
    def scorecard(request: Request) -> HTMLResponse:
        result = pilot.scorecard()
        return page(
            request,
            "scorecard.html.jinja",
            title="Итоги пилота",
            nav="scorecard",
            scorecard=result,
            margin=money(result.incremental_margin),
        )

    @app.post("/ask", response_class=HTMLResponse)
    def ask(request: Request, question: str = Form("")) -> HTMLResponse:
        if not question.strip():
            return page(
                request,
                "home.html.jinja",
                422,
                title="Отклонения и решения",
                nav="home",
                rows=views.home_rows(pilot),
                warnings=views.data_warnings(pilot),
                question_error="Введите вопрос",
            )
        answer = pilot.ask(question.strip())
        return page(
            request,
            "answer.html.jinja",
            title="Ответ на вопрос",
            question=question.strip(),
            answer=answer,
        )

    @app.post("/webhooks/metabase")
    def metabase(request: Request, background: BackgroundTasks) -> Response:
        secret = pilot.config.metabase_secret
        given = request.headers.get("Authorization", "")
        if not secret or not hmac.compare_digest(given, f"Bearer {secret}"):
            return Response(status_code=401)
        background.add_task(_run_rules, pilot)
        return Response(status_code=202)

    @app.post("/webhooks/bitrix24")
    async def bitrix24(request: Request) -> Response:
        form = {key: str(value) for key, value in (await request.form()).items()}
        status = await run_in_threadpool(pilot.handle_task_event, form)
        return Response(status_code=status)

    return app


def _decision(pilot: Pilot, decision_id: int) -> dict[str, Any]:
    try:
        with pilot.engine.connect() as conn:
            return get(conn, decision_id)
    except DecisionError as error:
        raise HTTPException(error.status, error.message) from error


def _run_rules(pilot: Pilot) -> None:
    pilot.run_rules()
    pilot.analyse_open()
