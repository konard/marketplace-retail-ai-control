@data-quality @pilot
Feature: Reconcile the data mart with the marketplace financial reports
  As the owner
  I want the system to prove its numbers match the marketplace's own report
  So that nobody acts on a confident explanation of wrong numbers (the pilot's main risk)

  Background:
    Given the reconciliation tolerance is 2%

  Rule: The computed payout must match the reported payout within the tolerance

    Scenario Outline: Reconcile one week of a channel
      Given the data mart has a computed "ozon" payout of <computed> for 2026-10-05 to 2026-10-11
      And the Ozon financial report shows a payout of <reported> for 2026-10-05 to 2026-10-11
      When the data is reconciled for 2026-10-05 to 2026-10-11
      Then the "ozon" reconciliation difference is <difference> and the status is "<status>"

      Examples:
        | computed  | reported  | difference | status   |
        | 98500.00  | 100000.00 | 1.5%       | ok       |
        | 102000.00 | 100000.00 | 2.0%       | ok       |
        | 97000.00  | 100000.00 | 3.0%       | mismatch |

    Scenario: A missing financial report is a mismatch, not a pass
      Given the data mart has a computed "ozon" payout of 98500.00 for 2026-10-05 to 2026-10-11
      When the data is reconciled for 2026-10-05 to 2026-10-11
      Then the "ozon" reconciliation status is "missing report"

  Rule: Recommendations are withheld while the data is not trusted

    Scenario: A channel that failed reconciliation gets no recommendations
      Given today is 2026-10-12
      And the "ozon" reconciliation status is "mismatch"
      And a "margin below plan" deviation is open for "SKU-1001" on "ozon"
      When the deviation is analysed
      Then no proposal is made and the deviation is marked "data check required"

    Scenario: The first two weeks of the pilot only reconcile data
      Given today is 2026-10-12
      And recommendations are enabled from 2026-10-19
      And the "ozon" reconciliation status is "ok"
      And a "margin below plan" deviation is open for "SKU-1001" on "ozon"
      When the deviation is analysed
      Then no proposal is made and the deviation is marked "reconciliation period"
