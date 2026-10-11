@pilot
Feature: Pilot scorecard and the continue-or-stop verdict
  As the owner
  I want the pilot measured against criteria fixed before it started
  So that I decide to continue or stop on facts, not on impressions

  Background:
    Given the pilot costs 150000.00
    And the largest reconciliation difference of the pilot is 1.5%
    And these decisions were made during the pilot:
      | status   | significant edit | lead time | incremental margin |
      | approved | no               | 1         | 60000.00           |
      | approved | no               | 2         | 40000.00           |
      | approved | no               | 2         | 30000.00           |
      | approved | no               | 3         | 20000.00           |
      | approved | no               | 1         | 15000.00           |
      | approved | no               | 2         | 10000.00           |
      | approved | no               | 3         | 5000.00            |
      | approved | yes              | 2         | 0.00               |
      | rejected | no               |           |                    |
      | rejected | no               |           |                    |

  Scenario: All criteria are met and the pilot pays for itself
    When the pilot scorecard is calculated
    Then the scorecard is:
      | criterion                                | target            | actual   | met |
      | Расхождение с отчётом маркетплейса       | ≤ 2,0%            | 1,5%     | да  |
      | Решения приняты без существенных правок  | ≥ 60%             | 70%      | да  |
      | Медианный срок исполнения                | ≤ 2 раб. дн.      | 2 раб. дн. | да |
      | Дополнительная маржа                     | ≥ 150 000 ₽       | 180 000 ₽ | да |
    And the verdict is "Пилот окупается: продолжать"

  Scenario: The pilot does not pay for itself
    Given the pilot costs 200000.00
    When the pilot scorecard is calculated
    Then the criterion "Дополнительная маржа" is not met
    And the verdict is "Пилот не окупился: остановить или сузить"

  Scenario: The pilot pays for itself, but the process criteria are missed
    Given the largest reconciliation difference of the pilot is 3.0%
    When the pilot scorecard is calculated
    Then the criterion "Расхождение с отчётом маркетплейса" is not met
    And the verdict is "Эффект есть, процесс не готов: продлить пилот и устранить причины"
