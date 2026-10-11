@follow-up
Feature: Measure the effect of an executed decision
  As the owner
  I want every executed decision checked against its target after 7 days
  So that the team learns what works and the pilot proves its value in money

  The effect is the change of the margin rate after the change date minus the
  change in a control group: SKUs on the same channel without decisions in the
  period (difference-in-differences).

  Background:
    Given "SKU-1001" has a unit cost of 440.00 from 2026-09-01
    And "SKU-2001" has a unit cost of 300.00 from 2026-09-01
    And these daily sales were loaded:
      | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
      | 2026-10-09 | 2026-10-12 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 9240.00     |
      | 2026-10-09 | 2026-10-19 | SKU-2001 | ozon    | 20    | 10000.00 | 1500.00    | 1000.00   | 0.00        |
    And a decision for "SKU-1001" on "ozon" with the target margin rate 12.0% and the guardrail sales drop 10.0%
    And the deviation of the decision started on 2026-10-09
    And the Bitrix24 task 501 of the decision was completed on 2026-10-13

  Rule: The result is compared with the period before and with the control group

    Scenario: The margin improved, but not enough to reach the target
      Given today is 2026-10-20
      And these daily sales were loaded:
        | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
        | 2026-10-13 | 2026-10-19 | SKU-1001 | ozon    | 47    | 42600.00 | 6390.00    | 4260.00   | 6243.20     |
      When the follow-ups run
      Then the follow-up compares:
        | metric              | before | after | change  |
        | margin rate         | 4.0%   | 11.8% | +7.8 pp |
        | units per day       | 50.0   | 47.0  | −6.0%   |
        | control margin rate | 15.0%  | 15.0% | +0.0 pp |
      And the effect against the control group is +7.8 pp
      And the incremental margin is 23259.60
      And the outcome is "partially achieved"
      And the result says "Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично"

  Rule: The result goes back to the task and decides the next step

    Scenario: A partial result is posted to the task and starts a next step
      Given today is 2026-10-20
      And these daily sales were loaded:
        | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
        | 2026-10-13 | 2026-10-19 | SKU-1001 | ozon    | 47    | 42600.00 | 6390.00    | 4260.00   | 6243.20     |
      When the follow-ups run
      Then Bitrix24 receives "task.commentitem.add" for task 501 with "Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично"
      And the decision status is "evaluated"
      And a next-step proposal linked to the decision is open

    Scenario: An achieved result closes the decision
      Given today is 2026-10-20
      And these daily sales were loaded:
        | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
        | 2026-10-13 | 2026-10-19 | SKU-1001 | ozon    | 47    | 42600.00 | 6390.00    | 4260.00   | 5817.20     |
      When the follow-ups run
      Then the outcome is "achieved"
      And the result says "Маржа 12,8% (было 4,0%), продажи −6,0%: цель достигнута"
      And the decision status is "closed"
      And no next-step proposal is open

    Scenario: The follow-up waits for 7 full days of data
      Given today is 2026-10-19
      When the follow-ups run
      Then the decision status is "done"
      And Bitrix24 receives no "task.commentitem.add" call

  Rule: The outcome depends on the target, the guardrail and the effect

    Scenario Outline: Classify the outcome for a 12.0% target and a 10.0% guardrail
      When the outcome is classified for a margin rate of <margin>, a sales change of <sales> and an effect of <effect>
      Then the outcome is "<outcome>"

      Examples:
        | margin | sales  | effect  | outcome            |
        | 12.8%  | −6.0%  | +8.8 pp | achieved           |
        | 11.8%  | −6.0%  | +7.8 pp | partially achieved |
        | 13.0%  | −15.0% | +9.0 pp | partially achieved |
        | 4.0%   | 0.0%   | +0.0 pp | not achieved       |
        | 12.5%  | −2.0%  | −0.5 pp | not achieved       |
