# marketplace-retail-ai-control

**Result: [Концепция AI-контура управления (docs/concept/README.md)](docs/concept/README.md)**
— a two-page concept, written in Russian, for a multichannel Wildberries and
Ozon retailer that runs 1C, Bitrix24, marketplace data and third-party
analytics. Sources and verification notes are in
[docs/concept/sources.md](docs/concept/sources.md).

The concept answers [issue #1](https://github.com/konard/marketplace-retail-ai-control/issues/1).
It describes one management loop, monitoring → analysis → decision →
execution → follow-up, for sales, profitability, costs and team performance.
The repository also holds the pilot from the concept: an executable
specification in Gherkin and a small Python implementation that passes it.

| Document | What is in it |
|---|---|
| [Concept](docs/concept/README.md) | two reference examples, the proposal, the pilot (Russian) |
| [Executable specification](features/README.md) | 16 features; every scenario is an automated test |
| [Architecture](docs/architecture/README.md) | context, modules, one morning, the life of a decision, data mart, deployment |
| [UX guidelines](docs/ux/README.md) | HAX, People + AI, NN/g, GOV.UK and WCAG 2.2 rules mapped to the scenarios that test them |

![The decision card: what happened, why, what to do, and the decision panel](docs/screenshots/web-card.png)

## Features

- **Concept.** Two sourced reference examples (Shopify Sidekick + Flow with
  the SNOCKS case; Bitrix24 BI Конструктор + BitrixGPT + robots), a
  build-vs-buy split, one end-to-end scenario and a 6–8 week pilot with a
  success metric, the main risk and open questions.
- **Specification first.** Every behaviour is a scenario in
  [`features/`](features/README.md), written before the code and run by
  [pytest-bdd](https://pytest-bdd.readthedocs.io/). The traceability table in
  `features/README.md` links each part of the concept to its feature.
- **The loop, implemented** in `src/retail_ai_control/`:
  - data from Wildberries, Ozon, 1C (OData) and an analytics CSV export into
    one mart, with SKU mapping and reconciliation against marketplace reports;
  - unit economics per SKU × channel × day and deviation rules for margin,
    advertising share, sales drop and stock cover;
  - an AI explanation and proposal built only from SQL evidence; an answer
    with an unsupported figure or an action outside the limits is replaced
    by a rule-based one;
  - a morning digest in the Bitrix24 chat, approval with edits or rejection
    with a reason, a Bitrix24 task with a checklist and a deadline;
  - a follow-up after 7 days against control SKUs: the decision is closed
    when the goal is achieved, otherwise a new proposal is made;
  - the decision journal, team results and the pilot scorecard.
- **Web app** for the decisions: server-rendered pages with FastAPI, Jinja
  and Pico CSS, no JavaScript, WCAG 2.2 AA basics tested on every page.
- **Ready parts instead of custom code:** httpx, SQLAlchemy Core, the
  OpenAI-compatible client (GigaChat, YandexGPT or a local model), Metabase
  alerts, Bitrix24 REST.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev,docs]"
```

See every screen on demo data, without connecting any system:

```bash
retail-ai-control --config examples/pilot.toml demo
retail-ai-control --config examples/pilot.toml serve --user 1
# open http://127.0.0.1:8000
```

The commands of the loop:

| Command | What it does |
|---|---|
| `retail-ai-control sync --from 2026-10-01 --to 2026-10-07` | load the sources for a date range |
| `retail-ai-control morning` | sync, reconcile, measure due effects, find deviations, propose, send the digest; run it daily from a systemd timer or cron |
| `retail-ai-control followup` | retry failed tasks and measure due effects |
| `retail-ai-control ask "почему упала маржа на Ozon?"` | ask a question about the data |
| `retail-ai-control serve` | the web app and the Metabase and Bitrix24 webhooks |

Add `--verbose` to log every step.

Run the specification, the tests and the same checks as CI:

```bash
pytest tests/bdd            # the Gherkin scenarios only
pytest                      # everything
ruff check . && ruff format --check . && mypy src tests/bdd
python scripts/check_file_size.py
bash scripts/check-required-docs.sh
sphinx-build -W --keep-going -b html docs _site
```

To check that the concept fits on two A4 pages, render it to PDF. This
requires Playwright and Chromium:

```bash
pip install playwright markdown && playwright install chromium
python experiments/render_concept_pdf.py
```

## Configuration

The pilot reads one TOML file: `--config`, `$RETAIL_AI_CONTROL_CONFIG` or
`pilot.toml`. [`examples/pilot.toml`](examples/pilot.toml) lists every
setting: rule thresholds, action limits, margin plans, approvers and the
manager of each channel. Tokens and passwords come only from environment
variables:

| Variable | Used for |
|---|---|
| `RETAIL_AI_WB_TOKEN` | Wildberries API |
| `RETAIL_AI_OZON_API_KEY` | Ozon Seller API |
| `RETAIL_AI_ONEC_PASSWORD` | 1C OData |
| `RETAIL_AI_LLM_API_KEY` | the OpenAI-compatible LLM API |
| `RETAIL_AI_BITRIX_WEBHOOK_URL` | Bitrix24 REST: chat and tasks |
| `RETAIL_AI_BITRIX_APPLICATION_TOKEN` | checks Bitrix24 task events |
| `RETAIL_AI_METABASE_SECRET` | checks Metabase alerts |
| `RETAIL_AI_DATABASE_URL` | overrides `database_url`, e.g. PostgreSQL in production |

Without `[llm] base_url` the loop runs on rules and labels its proposals
«Расчёт по правилам».

| Path | Purpose |
|---|---|
| `docs/concept/` | the concept (Russian, at most 2 pages) and its sources |
| `docs/architecture/`, `docs/ux/`, `docs/screenshots/` | architecture, UX guidelines, screenshots of every screen |
| `features/` | the executable specification |
| `src/retail_ai_control/` | the implementation |
| `tests/bdd/` | step definitions; `tests/test_concept_doc.py` checks the concept |
| `docs/preview-regeneration.md` | template note on preview regeneration (inherited) |

### Deploying API documentation

The `Docs` workflow (`.github/workflows/docs.yml`) builds the Sphinx site,
including the concept, on every push and pull request. It publishes the site
to GitHub Pages on `main` only when two things are set up:

- `Settings -> Pages -> Source` is set to `GitHub Actions`.
- The repository variable `DEPLOY_GITHUB_PAGES` is set to `true`.

The repository is based on the
[python-ai-driven-development-pipeline-template](https://github.com/link-foundation/python-ai-driven-development-pipeline-template).
Its CI/CD pipeline covers lint, tests, docs, links, security and workflow
audit. Its example package `src/my_package` is kept so those checks keep
running.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

- Change a scenario in `features/` first, see it fail, then change the code.
- Changes under `src/`, `tests/` or `scripts/` need a fragment in
  `changelog.d/`.
- Run the checks from [Quick Start](#quick-start) before you push.
- Keep the concept in Russian and within 2 pages; use Mermaid for diagrams
  and store images as files next to the document.

## License

[Unlicense](LICENSE) - Public Domain
