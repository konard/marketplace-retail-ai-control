@ui
Feature: Decision screens that follow human-AI interaction and usability guidelines
  As a busy owner or manager
  I want screens that show the most important thing first and make AI output easy to verify
  So that I decide quickly and only trust what I can check

  The rules come from docs/ux/README.md: Microsoft HAX guidelines, Google
  PAIR, Nielsen's heuristics and WCAG 2.2 AA.

  Background:
    Given today is 2026-10-12
    And the approvers are users 1 and 7
    And the deviation from the concept's example has a proposal

  Rule: Overview first, details on demand (digest -> card -> evidence)

    Scenario: The home page lists open deviations by impact
      When user 1 opens the home page
      Then the page title is "Отклонения и решения"
      And the first row shows "SKU-1001", "Ozon", "Маржа 4,0% при плане 15,0% — 3 дня подряд" and "14 520 ₽"
      And the row links to the decision card

    Scenario: The decision card answers the questions in the order a manager asks them
      When user 1 opens the decision card
      Then the card sections are in this order:
        | section             |
        | Что произошло       |
        | Почему              |
        | Что сделать         |
        | Ожидаемый эффект    |
        | Решение             |
      And the card shows a sparkline of the margin rate with a text alternative

    Scenario: Every figure can be traced to its data
      When user 1 opens the decision card
      And user 1 follows the evidence link of the cause
      Then the evidence page shows the SQL query and its result rows

  Rule: AI output is labelled and its limits are stated (HAX G1, G2, G11)

    Scenario: The card says who wrote the explanation
      When user 1 opens the decision card
      Then the explanation is labelled "Расчёт по правилам"
      And the card states "Цифры рассчитаны SQL-запросами; AI только объясняет их и предлагает действия в заданных пределах"

  Rule: The user stays in control and errors are easy to fix (HAX G9, Nielsen 3 and 9)

    Scenario: The approver can edit the proposed values before approving
      When user 1 opens the decision card
      Then the field "Изменить цену, %" has the value "5.0"
      And the button "Утвердить" is available

    Scenario: A rejection without a reason shows the error next to the field
      When user 1 rejects the proposal in the web app without a reason
      Then the page shows the error "Укажите причину отклонения" linked to the field "Причина отклонения"
      And the decision status is "proposed"

    Scenario: A user who is not an approver sees why they cannot decide
      When user 17 opens the decision card
      Then the button "Утвердить" is not available
      And the card states "Утверждать могут только назначенные руководители"

  Rule: The screens are accessible (WCAG 2.2 AA)

    Scenario Outline: Accessibility basics on every page
      When user 1 opens the <page>
      Then the page language is "ru"
      And every form field has a label
      And every status is shown as text, not only by colour
      And the page has one main landmark and one level-one heading

      Examples:
        | page           |
        | home page      |
        | decision card  |
        | team page      |
        | scorecard page |
