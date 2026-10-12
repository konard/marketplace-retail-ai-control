@analysis @ai
Feature: Explain a deviation and propose a fix
  As the manager who has to decide
  I want the cause of a deviation and a concrete fix with a measurable target
  So that I can decide in minutes and trust every number I see

  SQL computes every number. The AI only explains them and chooses actions
  within set limits. A rule-based analyst gives the same structure when the
  AI is unavailable or its answer fails validation.

  Background:
    Given today is 2026-10-12
    And the margin plan of "SKU-1001" on "ozon" is 15%
    And "SKU-1001" has a unit cost of 440.00 from 2026-09-01
    And these daily sales were loaded:
      | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
      | 2026-10-02 | 2026-10-08 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 3960.00     |
      | 2026-10-09 | 2026-10-11 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 9240.00     |
      | 2026-10-02 | 2026-10-11 | SKU-1001 | wb      | 50    | 50000.00 | 7500.00    | 5000.00   | 0.00        |
    And the deviation rules have run

  Rule: The analysis finds the cause in the numbers

    Scenario: The margin drop is decomposed by cost item
      When the deviation is analysed
      Then the cost share changes against the previous 7 days are:
        | item          | before | now   | change   |
        | commission    | 15.0%  | 15.0% | +0.0 pp  |
        | logistics     | 10.0%  | 10.0% | +0.0 pp  |
        | advertising   | 9.0%   | 21.0% | +12.0 pp |
        | cost of goods | 50.0%  | 50.0% | +0.0 pp  |
      And the main cause is "advertising"
      And the analysis notes that the unit price on "ozon" is 12.0% below "wb"

  Rule: The proposal has actions, a target and a guardrail

    Scenario: Propose to return the advertising share and raise the price
      When the deviation is analysed
      Then the proposal contains the actions:
        | action            | value |
        | set ad share      | 9.0%  |
        | change price      | +5.0% |
      And the target is a margin rate of at least 12.0%
      And the guardrail is a sales drop of at most 10.0%

    Scenario: Every figure has evidence that links to its SQL query
      When the deviation is analysed
      Then every figure in the analysis has evidence with a SQL query and its result rows

  Rule: AI output is accepted only when it is backed by the evidence and within limits

    Scenario: The AI agent investigates with tools and writes the explanation
      Given the AI model first calls the tool "margin_breakdown" and then answers:
        """
        {"explanation": "Маржа упала с 16,0% до 4,0%: доля рекламы выросла с 9,0% до 21,0% выручки. Цена на Ozon на 12,0% ниже, чем на WB.",
         "actions": [{"type": "set_ad_share", "value": 9.0}, {"type": "change_price", "value": 5.0}]}
        """
      When the deviation is analysed
      Then the explanation is "Маржа упала с 16,0% до 4,0%: доля рекламы выросла с 9,0% до 21,0% выручки. Цена на Ozon на 12,0% ниже, чем на WB."
      And the analysis is labelled "Сгенерировано AI"
      And the AI agent called the tool "margin_breakdown"

    Scenario: An AI explanation with a figure that is not in the evidence is rejected
      Given the AI model answers:
        """
        {"explanation": "Маржа упала из-за роста логистики на 7,5%.", "actions": []}
        """
      When the deviation is analysed
      Then the analysis is labelled "Расчёт по правилам"
      And the analysis log contains "unsupported figure 7,5"

    Scenario: An AI action outside the allowed limits is rejected
      Given the price change limit is 10%
      And the AI model answers:
        """
        {"explanation": "Цена на Ozon на 12,0% ниже, чем на WB.", "actions": [{"type": "change_price", "value": 30.0}]}
        """
      When the deviation is analysed
      Then the analysis is labelled "Расчёт по правилам"
      And the analysis log contains "change_price 30.0 exceeds limit 10.0"

    Scenario: The AI model is unavailable
      Given the AI model is unavailable
      When the deviation is analysed
      Then the analysis is labelled "Расчёт по правилам"
      And the proposal contains the actions:
        | action       | value |
        | set ad share | 9.0%  |
        | change price | +5.0% |

  Rule: The AI agent can only read data

    Scenario Outline: Writing SQL is refused
      When the AI agent runs the SQL "<sql>"
      Then the query is refused
      And the data mart still has 20 daily sales facts

      Examples:
        | sql                                   |
        | DELETE FROM sales_daily               |
        | UPDATE sales_daily SET revenue = 0    |
        | DROP TABLE sales_daily                |
        | SELECT 1; DELETE FROM sales_daily     |

    Scenario: Reading SQL is allowed
      When the AI agent runs the SQL "SELECT COUNT(*) AS n FROM sales_daily"
      Then the query returns the row "n=20"
