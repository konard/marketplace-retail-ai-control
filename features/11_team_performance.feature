@management
Feature: Team performance on decisions
  As the owner
  I want to see who executes decisions on time and whose decisions work
  So that I manage people by results, not by activity

  Background:
    Given today is 2026-10-20
    And these decision tasks exist:
      | responsible   | deadline   | completed  | outcome            |
      | Анна Смирнова | 2026-10-14 | 2026-10-13 | achieved           |
      | Анна Смирнова | 2026-10-14 | 2026-10-16 | not achieved       |
      | Олег Иванов   | 2026-10-15 | 2026-10-15 | partially achieved |
      | Олег Иванов   | 2026-10-16 |            |                    |

  Scenario: Performance per person
    When the team performance is calculated
    Then the team performance is:
      | responsible   | tasks | on time | overdue | effect achieved |
      | Анна Смирнова | 2     | 50%     | 0       | 50%             |
      | Олег Иванов   | 2     | 50%     | 1       | 0%              |

  Scenario: The owner sees the team page
    When the owner opens the team page
    Then the page shows a table with the caption "Исполнение решений по сотрудникам"
    And the row of "Олег Иванов" shows "Просрочено: 1"
