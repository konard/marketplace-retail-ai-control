@e2e
Feature: The full management loop on the concept's example
  As the owner
  I want one deviation to travel the whole loop without manual data work
  So that I see the pilot deliver: data, deviation, decision, task, measured effect

  This is reference example 2 from the concept: the Ozon advertising bid was
  raised, sales held, the margin fell from 16% to 4%.

  Background:
    Given the pilot is configured:
      | setting                 | value              |
      | approvers               | 1, 7               |
      | ozon manager            | 17 "Анна Смирнова" |
      | digest dialog           | chat42             |
      | margin plan SKU-1001    | 15%                |
      | web app                 | https://ai.example.ru |
    And the product catalog in 1C maps articles to marketplace IDs:
      | sku      | name            | wb_nm_id | ozon_sku |
      | SKU-1001 | T-shirt basic   | 111001   | 222001   |
      | SKU-2001 | Hoodie standard | 111002   | 222002   |
    And 1C publishes these cost prices:
      | sku      | valid_from | unit_cost |
      | SKU-1001 | 2026-09-01 | 440.00    |
      | SKU-2001 | 2026-09-01 | 300.00    |

  Scenario: From a margin drop to a measured result
    Given today is 2026-10-12
    And the marketplaces and the analytics service report these daily sales:
      | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
      | 2026-10-02 | 2026-10-08 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 3960.00     |
      | 2026-10-09 | 2026-10-11 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 9240.00     |
      | 2026-10-02 | 2026-10-11 | SKU-1001 | wb      | 50    | 50000.00 | 7500.00    | 5000.00   | 0.00        |
      | 2026-10-02 | 2026-10-11 | SKU-2001 | ozon    | 20    | 10000.00 | 1500.00    | 1000.00   | 0.00        |
    And the marketplace financial reports match the loaded sales
    When the morning run happens
    Then the digest in "chat42" contains "SKU-1001 · Ozon — Маржа 4,0% при плане 15,0% — 3 дня подряд"
    And the digest in "chat42" contains "Потери ≈ 14 520 ₽"
    When user 1 approves the proposal in the web app
    Then a Bitrix24 task for user 17 is due "2026-10-14T19:00:00+03:00"
    When the manager completes the Bitrix24 task on 2026-10-13
    And today is 2026-10-20
    And the marketplaces and the analytics service report these daily sales:
      | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
      | 2026-10-12 | 2026-10-12 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 9240.00     |
      | 2026-10-13 | 2026-10-19 | SKU-1001 | ozon    | 47    | 42600.00 | 6390.00    | 4260.00   | 6243.20     |
      | 2026-10-12 | 2026-10-19 | SKU-1001 | wb      | 50    | 50000.00 | 7500.00    | 5000.00   | 0.00        |
      | 2026-10-12 | 2026-10-19 | SKU-2001 | ozon    | 20    | 10000.00 | 1500.00    | 1000.00   | 0.00        |
    And the morning run happens
    Then the Bitrix24 task has the comment "Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично"
    And the decision journal shows the stages "proposed, approved, in progress, done, evaluated"
    And the pilot scorecard shows the incremental margin "23 260 ₽"
