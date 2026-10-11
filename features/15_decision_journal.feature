@management @journal
Feature: Weekly review of the decision journal
  As the owner or a manager
  I want every decision of a period with its result on one page
  So that once a week I see which decisions worked and what they earned

  The concept: "раз в неделю смотрят журнал решений и их эффект".

  Background:
    Given today is 2026-10-26
    And these decisions were made:
      | sku      | channel | decided on | status      | approved by | actions             | outcome            | incremental margin |
      | SKU-1001 | ozon    | 2026-10-12 | closed      | 1           | change price +3.0%  | achieved           | 6400.00            |
      | SKU-1002 | wb      | 2026-10-13 | evaluated   | 7           | set ad share 9.0%   | not achieved       | -1200.00           |
      | SKU-1003 | ozon    | 2026-10-20 | in progress | 1           | change price +5.0%  |                    |                    |
      | SKU-1004 | wb      | 2026-10-21 | rejected    | 1           | change price -5.0%  |                    |                    |
      | SKU-1005 | ozon    | 2026-09-14 | closed      | 1           | restock 300         | partially achieved | 900.00             |

  Rule: The journal shows the decisions of a period, newest first

    Scenario: By default the journal shows the last four weeks
      When the owner opens the decision journal
      Then the period is 2026-09-28 to 2026-10-25
      And the journal lists:
        | Дата       | Товар    | Канал | Что сделать                   | Статус                 | Эффект   |
        | 21.10.2026 | SKU-1004 | WB    | Изменить цену на −5,0%        | Отклонено              | —        |
        | 20.10.2026 | SKU-1003 | Ozon  | Изменить цену на +5,0%        | В работе               | —        |
        | 13.10.2026 | SKU-1002 | WB    | Снизить долю рекламы до 9,0%  | Эффект измерен         | −1 200 ₽ |
        | 12.10.2026 | SKU-1001 | Ozon  | Изменить цену на +3,0%        | Цель достигнута        | 6 400 ₽  |

    Scenario: The owner reviews one week
      When the owner opens the decision journal from 2026-10-12 to 2026-10-18
      Then the journal lists the SKUs "SKU-1002, SKU-1001"
      And the journal summary is "Решений: 2 · эффект измерен: 2 · цель достигнута: 1 · дополнительная маржа: 5 200 ₽"

    Scenario: Each decision opens its decision card
      When the owner opens the decision journal
      Then the row of "SKU-1001" links to its decision card

  Rule: A wrong period is explained next to the field (Nielsen 9)

    Scenario: The start of the period is after its end
      When the owner opens the decision journal from 2026-10-18 to 2026-10-12
      Then the page shows the error "Начало периода позже конца" linked to the field "С"
      And the error summary at the top of the page links to the field "С"
      And the journal is empty
