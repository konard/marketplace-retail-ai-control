@execution @bitrix24
Feature: Turn an approved decision into a Bitrix24 task and track it
  As the owner
  I want every approved decision to become a task with an owner, a deadline and a success criterion
  So that decisions are executed, not forgotten in a chat

  Background:
    Given today is 2026-10-12
    And the approvers are users 1 and 7
    And the "ozon" channel manager is user 17 "Анна Смирнова"
    And the web app runs at "https://ai.example.ru"
    And a proposal for "SKU-1001" on "ozon" contains the actions:
      | action       | value |
      | set ad share | 9.0%  |
      | change price | +5.0% |

  Rule: Approval creates a task for the channel manager

    Scenario: The task carries the actions, the deadline and the success criterion
      When user 1 approves the proposal
      Then Bitrix24 receives "tasks.task.add" with the fields:
        | field          | value                                            |
        | TITLE          | Маржа SKU-1001 на Ozon: реклама 9,0%, цена +5,0% |
        | RESPONSIBLE_ID | 17                                               |
        | CREATED_BY     | 1                                                |
        | DEADLINE       | 2026-10-14T19:00:00+03:00                        |
      And the task description contains "Критерий успеха: маржа ≥ 12,0% при падении продаж ≤ 10,0% за 7 дней"
      And the task description contains "https://ai.example.ru/decisions/1"
      And Bitrix24 receives "task.checklistitem.add" for each action:
        | title                           |
        | Снизить долю рекламы до 9,0%    |
        | Изменить цену на +5,0%          |
      And the decision status is "in progress"

    Scenario Outline: The deadline is two business days after approval
      Given today is <approved>
      When user 1 approves the proposal
      Then the task deadline is "<deadline>"

      Examples:
        | approved   | deadline                  |
        | 2026-10-12 | 2026-10-14T19:00:00+03:00 |
        | 2026-10-15 | 2026-10-19T19:00:00+03:00 |
        | 2026-10-16 | 2026-10-20T19:00:00+03:00 |

  Rule: Bitrix24 outages do not lose or duplicate tasks

    Scenario: The task is created on retry after Bitrix24 was unavailable
      Given Bitrix24 answers 503 to the next "tasks.task.add" call
      When user 1 approves the proposal
      Then the decision status is "approved"
      When the pending tasks are retried
      And the pending tasks are retried
      Then Bitrix24 created exactly 1 task
      And the decision status is "in progress"

  Rule: Bitrix24 tells the system when the task is done

    Scenario: The manager completes the task
      Given user 1 approved the proposal
      And the Bitrix24 task has status 5 "completed" closed on 2026-10-13
      When Bitrix24 sends the "ONTASKUPDATE" event for the task with the correct application token
      Then the decision status is "done"
      And the change date is 2026-10-13
      And the follow-up is due on 2026-10-20

    Scenario: An update that does not complete the task keeps it in progress
      Given user 1 approved the proposal
      And the Bitrix24 task has status 3 "in progress"
      When Bitrix24 sends the "ONTASKUPDATE" event for the task with the correct application token
      Then the decision status is "in progress"

    Scenario: An event with a wrong application token is ignored
      Given user 1 approved the proposal
      When Bitrix24 sends the "ONTASKUPDATE" event for the task with a wrong application token
      Then the event endpoint answers 401
      And the decision status is "in progress"
