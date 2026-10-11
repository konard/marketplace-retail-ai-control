@monitoring
Feature: Detect deviations in sales, margin, costs and stock
  As the owner
  I want the system to find problems for me every morning
  So that I do not have to scan dashboards to notice them

  Background:
    Given today is 2026-10-12
    And the margin plan of "SKU-1001" on "ozon" is 15%

  Rule: Margin below plan for 3 days in a row is a deviation

    Scenario: Three days below plan raise a deviation
      Given "SKU-1001" on "ozon" had daily revenue of 8800.00 with these margin rates:
        | day        | margin_pct |
        | 2026-10-09 | 4.0%       |
        | 2026-10-10 | 4.0%       |
        | 2026-10-11 | 4.0%       |
      When the deviation rules run
      Then a "margin below plan" deviation is open for "SKU-1001" on "ozon"
      And the deviation says "Маржа 4,0% при плане 15,0% — 3 дня подряд"
      And the deviation impact is 2904.00

    Scenario: Two days below plan are not yet a deviation
      Given "SKU-1001" on "ozon" had daily revenue of 8800.00 with these margin rates:
        | day        | margin_pct |
        | 2026-10-09 | 16.0%      |
        | 2026-10-10 | 4.0%       |
        | 2026-10-11 | 4.0%       |
      When the deviation rules run
      Then no "margin below plan" deviation is open for "SKU-1001" on "ozon"

  Rule: Stock that covers fewer days than the lead time is a stockout risk

    Background:
      Given "SKU-1001" on "wb" sold 5 units a day for the last 14 days with a daily margin of 1000.00
      And the minimum stock cover is 14 days

    Scenario: Stock for 8 days when 14 are needed
      Given the stock of "SKU-1001" on "wb" on 2026-10-11 was 40
      When the deviation rules run
      Then a "stockout risk" deviation is open for "SKU-1001" on "wb"
      And the deviation says "Остатка хватит на 8 дн. при норме 14 дн."
      And the deviation impact is 6000.00

    Scenario: Stock for 20 days is enough
      Given the stock of "SKU-1001" on "wb" on 2026-10-11 was 100
      When the deviation rules run
      Then no "stockout risk" deviation is open for "SKU-1001" on "wb"

  Rule: A week-over-week sales drop above the threshold is a deviation

    Scenario: Revenue fell by 30% compared with the previous week
      Given the sales drop threshold is 20%
      And "SKU-2001" on "wb" had revenue of 70000.00 at a 20.0% margin rate in the week before last
      And "SKU-2001" on "wb" had revenue of 49000.00 in the last week
      When the deviation rules run
      Then a "sales drop" deviation is open for "SKU-2001" on "wb"
      And the deviation says "Выручка за 7 дней −30,0% к прошлой неделе"
      And the deviation impact is 4200.00

  Rule: Advertising above its share limit is a cost deviation, unless the margin rule already covers it

    Scenario: High advertising share on a profitable SKU
      Given the advertising share limit is 15%
      And the margin plan of "SKU-2001" on "ozon" is 10%
      And "SKU-2001" on "ozon" spent 18% of revenue 10000.00 on advertising on each of the last 3 days at a 20.0% margin rate
      When the deviation rules run
      Then an "advertising above limit" deviation is open for "SKU-2001" on "ozon"
      And the deviation impact is 900.00

    Scenario: The margin deviation already explains the advertising cost
      Given the advertising share limit is 15%
      And "SKU-1001" on "ozon" spent 21% of revenue 8800.00 on advertising on each of the last 3 days at a 4.0% margin rate
      When the deviation rules run
      Then a "margin below plan" deviation is open for "SKU-1001" on "ozon"
      And no "advertising above limit" deviation is open for "SKU-1001" on "ozon"

  Rule: The same problem is reported once until it is resolved

    Scenario: Running the rules again does not duplicate an open deviation
      Given "SKU-1001" on "ozon" had daily revenue of 8800.00 with these margin rates:
        | day        | margin_pct |
        | 2026-10-09 | 4.0%       |
        | 2026-10-10 | 4.0%       |
        | 2026-10-11 | 4.0%       |
      When the deviation rules run
      And the deviation rules run
      Then exactly 1 "margin below plan" deviation is open for "SKU-1001" on "ozon"

  Rule: A Metabase alert can trigger the rules through a signed webhook

    Scenario: A Metabase alert with the shared secret runs the rules
      Given "SKU-1001" on "ozon" had daily revenue of 8800.00 with these margin rates:
        | day        | margin_pct |
        | 2026-10-09 | 4.0%       |
        | 2026-10-10 | 4.0%       |
        | 2026-10-11 | 4.0%       |
      When Metabase posts an alert for the question "Маржа ниже плана" with the correct secret
      Then the webhook answers 202
      And a "margin below plan" deviation is open for "SKU-1001" on "ozon"

    Scenario: A webhook call without the secret is refused
      When Metabase posts an alert for the question "Маржа ниже плана" with a wrong secret
      Then the webhook answers 401
      And no deviations are open
