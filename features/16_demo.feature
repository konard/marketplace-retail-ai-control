@demo
Feature: Try the whole loop on demo data
  As someone who evaluates the pilot
  I want example data that fills every screen
  So that I can see the loop before 1C, the marketplaces and Bitrix24 are connected

  The command "retail-ai-control demo" loads the concept's example of today
  and four weeks of decisions that the loop has already measured.

  Background:
    Given today is 2026-10-12
    And the margin plan of "SKU-1001" on "ozon" is 15.0%
    And the "ozon" channel manager is user 17 "Анна Смирнова"
    And the "wb" channel manager is user 18 "Олег Петров"
    And the demo data is loaded

  Scenario: Today's deviations are the concept's example, each with a proposal
    Then a "margin below plan" deviation is open for "SKU-1001" on "ozon"
    And a "stockout risk" deviation is open for "SKU-1001" on "wb"
    And every open deviation has a proposal

  Scenario: A decision that missed its goal is proposed again, as the loop does
    Then the decision for "SKU-1003" on "ozon" is "evaluated" with the outcome "not achieved"
    And a "advertising above limit" deviation is open for "SKU-1003" on "ozon"
    And the new proposal for "SKU-1003" follows the evaluated decision

  Scenario: The journal shows the decisions of the last four weeks with their effect
    When the visitor opens the decision journal
    Then the journal summary is "Решений: 4 · эффект измерен: 3 · цель достигнута: 2 · дополнительная маржа: 8 100 ₽"

  Scenario: The team page shows who executes decisions on time
    When the visitor opens the team page
    Then the team table lists:
      | Сотрудник     | Задачи | В срок | Просрочено | Цель достигнута |
      | Анна Смирнова | 2      | 50%    | 1          | 0%              |
      | Олег Петров   | 2      | 100%   | 0          | 100%            |

  Scenario: The scorecard measures every pilot criterion
    When the visitor opens the scorecard page
    Then every criterion of the scorecard has a measured value
