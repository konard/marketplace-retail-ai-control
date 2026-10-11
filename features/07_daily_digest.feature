@owner @digest
Feature: Morning digest in the Bitrix24 chat
  As the owner or a manager
  I want the 3-5 most important deviations every morning where I already work
  So that I spend my attention on what costs the most money

  Background:
    Given today is 2026-10-12
    And the digest is sent to the Bitrix24 dialog "chat42"
    And the digest shows at most 5 deviations

  Scenario: The deviations with the largest impact come first
    Given these deviations are open:
      | rule              | sku      | channel | impact   |
      | margin below plan | SKU-1001 | ozon    | 14520.00 |
      | stockout risk     | SKU-1002 | wb      | 6000.00  |
      | sales drop        | SKU-2001 | wb      | 4200.00  |
      | margin below plan | SKU-1003 | wb      | 900.00   |
      | stockout risk     | SKU-1004 | ozon    | 25000.00 |
      | sales drop        | SKU-1005 | ozon    | 300.00   |
      | margin below plan | SKU-1006 | ozon    | 1200.00  |
    When the morning digest is built
    Then the digest lists these SKUs in order:
      | sku      |
      | SKU-1004 |
      | SKU-1001 |
      | SKU-1002 |
      | SKU-2001 |
      | SKU-1006 |
    And the digest contains "Ещё 2 отклонения — в журнале решений"

  Scenario: Each item says what happened, what it costs and where to decide
    Given these deviations are open:
      | rule              | sku      | channel | impact   | summary                                  |
      | margin below plan | SKU-1001 | ozon    | 14520.00 | Маржа 4,0% при плане 15,0% — 3 дня подряд |
    When the morning digest is built
    Then the digest contains "SKU-1001 · Ozon — Маржа 4,0% при плане 15,0% — 3 дня подряд"
    And the digest contains "Потери ≈ 14 520 ₽"
    And the digest links to the decision card of the deviation for "SKU-1001"

  Scenario: The digest is posted to the owner's chat
    Given these deviations are open:
      | rule              | sku      | channel | impact   |
      | margin below plan | SKU-1001 | ozon    | 14520.00 |
    When the morning digest is sent
    Then Bitrix24 receives "im.message.add" with DIALOG_ID "chat42"
    And the message starts with "[B]Сводка на 12.10.2026[/B]"

  Scenario: A quiet day still gets a digest
    When the morning digest is sent
    Then Bitrix24 receives "im.message.add" with DIALOG_ID "chat42"
    And the digest contains "Отклонений нет."

  Scenario: The digest reports data problems, outcomes and overdue tasks
    Given the "ozon" reconciliation status is "mismatch"
    And a decision for "SKU-1001" on "ozon" was evaluated as "partially achieved" with the result "Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично"
    And the task "Маржа SKU-3001 на WB: цена +2,0%" of "Олег Иванов" was due on 2026-10-09 and is not completed
    When the morning digest is built
    Then the digest contains "Данные Ozon не сверены с отчётом маркетплейса — рекомендации по Ozon приостановлены"
    And the digest contains "SKU-1001 · Ozon: Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично"
    And the digest contains "Просрочено: Маржа SKU-3001 на WB: цена +2,0% — Олег Иванов, срок 09.10.2026"
