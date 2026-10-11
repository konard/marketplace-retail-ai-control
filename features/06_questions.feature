@ai @owner
Feature: Ask questions about the business in plain language
  As the owner
  I want to ask "why" questions in my own words
  So that I get an answer with numbers I can check, without building a report

  Background:
    Given today is 2026-10-12
    And "SKU-1001" has a unit cost of 440.00 from 2026-09-01
    And these daily sales were loaded:
      | from       | to         | sku      | channel | units | revenue  | commission | logistics | advertising |
      | 2026-10-02 | 2026-10-08 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 3960.00     |
      | 2026-10-09 | 2026-10-11 | SKU-1001 | ozon    | 50    | 44000.00 | 6600.00    | 4400.00   | 9240.00     |

  Scenario: The owner asks why the Ozon margin fell
    Given the AI model first calls the tool "margin_by_channel" and then answers:
      """
      {"answer": "Маржа Ozon за последние 3 дня — 4,0% против 16,0% неделей раньше: выросла доля рекламы."}
      """
    When the owner asks "Почему упала маржа на Ozon?"
    Then the answer is "Маржа Ozon за последние 3 дня — 4,0% против 16,0% неделей раньше: выросла доля рекламы."
    And the answer links to the evidence of the query "margin_by_channel"

  Scenario: An answer with figures that the data does not back is not shown
    Given the AI model first calls the tool "margin_by_channel" and then answers:
      """
      {"answer": "Маржа Ozon упала до 2,5%."}
      """
    When the owner asks "Почему упала маржа на Ozon?"
    Then the answer is "Не удалось подтвердить цифры ответа данными. Проверьте дашборд."
    And the answer links to the dashboard

  Scenario: The AI model is unavailable
    Given the AI model is unavailable
    When the owner asks "Почему упала маржа на Ozon?"
    Then the answer is "AI-ассистент сейчас недоступен. Данные — в дашборде."
    And the answer links to the dashboard
