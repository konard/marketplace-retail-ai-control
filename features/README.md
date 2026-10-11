# Executable specification

These Gherkin files are the requirements for the pilot from
[the concept](../docs/concept/README.md). Every scenario runs as an automated
test with [pytest-bdd](https://pytest-bdd.readthedocs.io/). The step
definitions are in [`tests/bdd/`](../tests/bdd/), and the implementation is in
[`src/retail_ai_control/`](../src/retail_ai_control/).

## How we work

1. Write or change a scenario here first. Use the business language and
   real numbers that a person can check with a calculator.
2. Run `pytest tests/bdd` and see the new scenario fail.
3. Write the smallest code that makes it pass, then refactor.

## Conventions

- Feature and step text is in English. Texts that users see (messages,
  digest, task titles) are in Russian, exactly as the system writes them.
- `Rule:` groups scenarios by one business rule. `Background:` holds the
  facts every scenario of the feature needs.
- Money is in rubles with two decimals. Rates are shown with one decimal,
  for example `4.0%`, and differences of rates in percentage points (`pp`).
- External systems (Wildberries, Ozon, 1C, Bitrix24, the AI model) are
  replaced by fakes at the HTTP level. The production code runs unchanged.
- Tags: `@data`, `@economics`, `@data-quality`, `@monitoring`, `@analysis`,
  `@ai`, `@owner`, `@digest`, `@decisions`, `@approval`, `@execution`,
  `@bitrix24`, `@follow-up`, `@management`, `@journal`, `@pilot`, `@e2e`,
  `@ui`, `@demo`.
  Run one group with `pytest tests/bdd -m digest`.

## Traceability to the concept

| Concept: loop stage or pilot item | Feature |
|---|---|
| Data: 1C, WB, Ozon, analytics service into one mart | [01_data_collection](01_data_collection.feature) |
| Unit economics per SKU × channel × day | [02_unit_economics](02_unit_economics.feature) |
| Pilot risk "wrong numbers": reconciliation, weeks 1-2 | [03_reconciliation](03_reconciliation.feature) |
| Monitoring: deviations instead of reports | [04_deviation_detection](04_deviation_detection.feature) |
| AI layer: cause, proposal, evidence, limits | [05_ai_analysis](05_ai_analysis.feature) |
| AI layer: questions in plain language | [06_questions](06_questions.feature) |
| Morning digest in Bitrix24 | [07_daily_digest](07_daily_digest.feature) |
| Decision by a person | [08_decision_approval](08_decision_approval.feature) |
| Execution: Bitrix24 task with a deadline | [09_task_execution](09_task_execution.feature) |
| Control of the effect after 7 days | [10_follow_up](10_follow_up.feature) |
| Managing the team by results | [11_team_performance](11_team_performance.feature) |
| Weekly review of the decision journal and its effect | [15_decision_journal](15_decision_journal.feature) |
| Pilot success criteria and the verdict | [12_pilot_scorecard](12_pilot_scorecard.feature) |
| Reference example 2 through the whole loop | [13_end_to_end](13_end_to_end.feature) |
| Screens and UX rules | [14_user_interface](14_user_interface.feature) |
| Trying the loop on demo data before the systems are connected | [16_demo](16_demo.feature) |
