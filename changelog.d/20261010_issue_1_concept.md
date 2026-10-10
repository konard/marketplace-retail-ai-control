### Added

- Add the issue #1 concept of an AI management loop for a Wildberries and Ozon
  retailer (`docs/concept/`, in Russian) with two sourced reference examples,
  Mermaid diagrams, screenshots, and a sources appendix; render it in Sphinx
  with `sphinxcontrib-mermaid`, replace the template README with a project
  README that links to the result first, and test the concept's structure and
  length budget.

### Fixed

- Skip `actions/dependency-review-action` with a warning when the repository's
  Dependency graph is disabled (`scripts/check-dependency-graph.sh` probes the
  SBOM endpoint), instead of failing every pull request with "Dependency review
  is not supported on this repository". Unknown probe answers still run the
  review.
