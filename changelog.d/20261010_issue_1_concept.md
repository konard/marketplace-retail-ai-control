### Added

- Add the issue #1 concept of an AI management loop for a Wildberries and Ozon
  retailer (`docs/concept/`, in Russian) with two sourced reference examples,
  Mermaid diagrams, screenshots, and a sources appendix; render it in Sphinx
  with `sphinxcontrib-mermaid`, replace the template README with a project
  README that links to the result first, and test the concept's structure and
  length budget.
- Add the pilot from the concept as an executable specification and its
  implementation: 16 Gherkin features in `features/` run by pytest-bdd, and the
  `retail_ai_control` package with connectors for Wildberries, Ozon, 1C OData
  and an analytics CSV, a data mart with unit economics, deviation rules, an
  evidence-checked AI agent with a rule-based fallback, Bitrix24 digest, tasks
  and follow-up, the decision journal, the pilot scorecard, a FastAPI web app
  and the `retail-ai-control` CLI with a `demo` command.
- Add the architecture (`docs/architecture/`) with styled Mermaid diagrams, UX
  guidelines mapped to the scenarios that test them (`docs/ux/`), screenshots of
  every screen, and a README describing the spec, the implementation and the
  demo.

### Fixed

- Skip `actions/dependency-review-action` with a warning when the repository's
  Dependency graph is disabled (`scripts/check-dependency-graph.sh` probes the
  SBOM endpoint), instead of failing every pull request with "Dependency review
  is not supported on this repository". Unknown probe answers still run the
  review.
