@decisions @approval
Feature: Approve, edit or reject a proposed decision
  As the owner or a person the owner trusts to approve
  I want to approve, edit or reject a proposal with one action
  So that a person, not the AI, is accountable for every change

  Background:
    Given today is 2026-10-12
    And the approvers are users 1 and 7
    And the "ozon" channel manager is user 17 "Анна Смирнова"
    And a proposal for "SKU-1001" on "ozon" contains the actions:
      | action       | value |
      | set ad share | 9.0%  |
      | change price | +5.0% |

  Rule: Only an approver decides, and only once

    Scenario: The owner approves the proposal as it is
      When user 1 approves the proposal
      Then the decision status is "approved"
      And the decision was approved by user 1 without significant edits
      And the decision journal records "approved" by user 1

    Scenario: A user who is not an approver cannot approve
      When user 17 approves the proposal
      Then the request is refused with status 403
      And the decision status is "proposed"

    Scenario: A decision cannot be approved twice
      Given user 1 approved the proposal
      When user 7 approves the proposal
      Then the request is refused with status 409
      And the decision journal records "approved" exactly once

  Rule: Edits are allowed; large edits are counted for the pilot scorecard

    Scenario Outline: The approver edits the actions before approving
      When user 1 approves the proposal with the actions:
        | action   | value   |
        | <action> | <value> |
      Then the decision status is "approved"
      And the edit is <significance>

      Examples:
        | action       | value | significance    |
        | change price | +3.0% | not significant |
        | change price | +2.0% | significant     |
        | set ad share | 9.0%  | significant     |

  Rule: A rejection always has a reason

    Scenario: Rejecting without a reason is not accepted
      When user 1 rejects the proposal without a reason
      Then the request is refused with the message "Укажите причину отклонения"
      And the decision status is "proposed"

    Scenario: Rejecting with a reason closes the proposal
      When user 1 rejects the proposal with the reason "Идёт акция до конца недели"
      Then the decision status is "rejected"
      And the decision journal records "rejected" by user 1 with "Идёт акция до конца недели"
