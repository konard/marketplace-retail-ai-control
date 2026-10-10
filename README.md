# marketplace-retail-ai-control

**Result: [Концепция AI-контура управления (docs/concept/README.md)](docs/concept/README.md)**
— a short concept, written in Russian, for a multichannel Wildberries and Ozon
retailer that runs 1C, Bitrix24, marketplace data and third-party analytics.
Sources and verification notes are in [docs/concept/sources.md](docs/concept/sources.md).

The concept answers [issue #1](https://github.com/konard/marketplace-retail-ai-control/issues/1).
It describes one management loop, monitoring → analysis → decision →
execution → follow-up, for sales, profitability, costs and team performance.

## Features

- **Two sourced reference examples:**
  - Shopify Sidekick + Flow, with the SNOCKS case study.
  - Bitrix24 BI Конструктор + BitrixGPT + robots.

  Each one covers what it does, the AI's role, what to adopt, its limitations,
  a screenshot, and a Mermaid diagram of its process.
- **A proposal for the company:**
  - a build-vs-buy split;
  - daily use by the owner, managers and employees;
  - one end-to-end scenario: detect → suggest a fix → a person approves →
    the task is completed → the outcome is checked;
  - a 6–8 week pilot with a success metric, the main risk and open questions.
- **Stack:** Python connectors to 1C, Bitrix24 and the marketplace APIs →
  PostgreSQL → Metabase alerts → an LLM agent with tool calling → tasks
  created through the Bitrix24 task API.
- **Automated checks** keep the concept in shape: required sections, Mermaid
  diagrams, image files next to the document, the length budget, and a README
  that links to the result first.

## Quick Start

Read the result on GitHub: [docs/concept/README.md](docs/concept/README.md).
GitHub renders the Mermaid diagrams inline.

To build the documentation site locally (Sphinx + MyST + Mermaid):

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev,docs]"

sphinx-build -W --keep-going -b html docs _site
```

To run the same checks as CI:

```bash
ruff check . && ruff format --check . && mypy src/
python scripts/check_file_size.py
bash scripts/check-required-docs.sh
pytest
```

To check that the concept fits on two A4 pages, render it to PDF. This
requires Playwright and Chromium:

```bash
pip install playwright markdown && playwright install chromium
python experiments/render_concept_pdf.py
```

## Configuration

| Path | Purpose |
|---|---|
| `docs/concept/README.md` | The deliverable (Russian, at most 2 pages) |
| `docs/concept/sources.md` | Source and verification appendix (outside the page limit) |
| `docs/concept/*.png` | Screenshots used by the concept |
| `docs/conf.py`, `docs/requirements.txt` | Sphinx with `myst_parser` and `sphinxcontrib-mermaid` |
| `tests/test_concept_doc.py` | Structure and length checks for the concept |
| `docs/preview-regeneration.md` | Template note on preview regeneration (inherited) |

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
running. Code, service setup and detailed architecture are out of scope for
this phase.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

- Changes under `src/`, `tests/` or `scripts/` need a fragment in
  `changelog.d/`.
- Run the checks from [Quick Start](#quick-start) before you push.
- Keep the concept within 2 pages.
- Write the concept in Russian, use Mermaid for diagrams, and store images as
  files next to the document.

## License

[Unlicense](LICENSE) - Public Domain
