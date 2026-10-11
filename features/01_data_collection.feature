@data
Feature: Collect sales, costs, stock and advertising data into one data mart
  As the owner of a Wildberries and Ozon store
  I want the figures from 1C, the marketplaces and the analytics service in one place
  So that every later step works on the same numbers: SKU x channel x day

  Background:
    Given the product catalog in 1C maps articles to marketplace IDs:
      | sku      | name            | wb_nm_id | ozon_sku |
      | SKU-1001 | T-shirt basic   | 111001   | 222001   |
      | SKU-2001 | Hoodie standard | 111002   | 222002   |

  Rule: Every source is converted to daily facts per SKU and channel

    Scenario: Load a Wildberries realization report
      Given the Wildberries realization report contains:
        | rr_dt      | nm_id  | doc_type_name | quantity | retail_amount | ppvz_for_pay | delivery_rub |
        | 2026-10-11 | 111001 | Продажа       | 2        | 2000.00       | 1700.00      | 200.00       |
        | 2026-10-11 | 111001 | Продажа       | 1        | 1000.00       | 850.00       | 100.00       |
        | 2026-10-11 | 111001 | Возврат       | 1        | 1000.00       | 850.00       | 50.00        |
      When the data is synchronized for 2026-10-11
      Then the data mart contains for "SKU-1001" on "wb" on 2026-10-11:
        | units | revenue | commission | logistics |
        | 2     | 2000.00 | 300.00     | 350.00    |

    Scenario: Load Ozon finance transactions
      Given the Ozon finance transactions contain:
        | operation_date | operation_type                    | sku    | accruals_for_sale | sale_commission | services_total |
        | 2026-10-11     | OperationAgentDeliveredToCustomer | 222001 | 880.00            | -132.00         | -88.00         |
        | 2026-10-11     | OperationAgentDeliveredToCustomer | 222001 | 880.00            | -132.00         | -88.00         |
        | 2026-10-11     | ClientReturnAgentOperation        | 222001 | -880.00           | 132.00          | -40.00         |
      When the data is synchronized for 2026-10-11
      Then the data mart contains for "SKU-1001" on "ozon" on 2026-10-11:
        | units | revenue | commission | logistics |
        | 1     | 880.00  | 132.00     | 216.00    |

    Scenario: Load cost prices from 1C through the standard OData interface
      Given 1C publishes these cost prices:
        | sku      | valid_from | unit_cost |
        | SKU-1001 | 2026-09-01 | 440.00    |
        | SKU-2001 | 2026-09-01 | 300.00    |
      When the data is synchronized for 2026-10-11
      Then the unit cost of "SKU-1001" on 2026-10-11 is 440.00

    Scenario: Load advertising spend from the analytics service export
      Given the analytics service export contains:
        | date       | channel | sku      | spend   |
        | 2026-10-11 | ozon    | SKU-1001 | 1848.00 |
      When the data is synchronized for 2026-10-11
      Then the data mart contains for "SKU-1001" on "ozon" on 2026-10-11:
        | advertising |
        | 1848.00     |

    Scenario: Load stock levels from both marketplaces
      Given the marketplaces report stock on 2026-10-11:
        | channel | sku      | stock |
        | wb      | SKU-1001 | 40    |
        | ozon    | SKU-1001 | 25    |
      When the data is synchronized for 2026-10-11
      Then the stock of "SKU-1001" on "ozon" on 2026-10-11 is 25

  Rule: Reloading is safe and data problems are visible, never silent

    Scenario: A recalculated marketplace report replaces the earlier figures
      Given the Wildberries realization report contains:
        | rr_dt      | nm_id  | doc_type_name | quantity | retail_amount | ppvz_for_pay | delivery_rub |
        | 2026-10-11 | 111001 | Продажа       | 1        | 1000.00       | 850.00       | 100.00       |
      And the data was synchronized for 2026-10-11
      When the marketplace recalculates the report to:
        | rr_dt      | nm_id  | doc_type_name | quantity | retail_amount | ppvz_for_pay | delivery_rub |
        | 2026-10-11 | 111001 | Продажа       | 3        | 3000.00       | 2550.00      | 300.00       |
      And the data is synchronized for 2026-10-11
      Then the data mart contains for "SKU-1001" on "wb" on 2026-10-11:
        | units | revenue |
        | 3     | 3000.00 |
      And the data mart has exactly 1 fact for "SKU-1001" on "wb" on 2026-10-11

    Scenario: Rows for unknown marketplace IDs go to the data quality report
      Given the Wildberries realization report contains:
        | rr_dt      | nm_id  | doc_type_name | quantity | retail_amount | ppvz_for_pay | delivery_rub |
        | 2026-10-11 | 999999 | Продажа       | 1        | 500.00        | 400.00       | 50.00        |
      When the data is synchronized for 2026-10-11
      Then the data quality report lists unmapped ID "999999" on "wb" with revenue 500.00

    Scenario: A failing source does not stop the other sources
      Given the Wildberries realization report contains:
        | rr_dt      | nm_id  | doc_type_name | quantity | retail_amount | ppvz_for_pay | delivery_rub |
        | 2026-10-11 | 111001 | Продажа       | 1        | 1000.00       | 850.00       | 100.00       |
      And the Ozon API answers with HTTP 503
      When the data is synchronized for 2026-10-11
      Then the sync report shows "ozon" as failed with "503"
      And the sync report shows "wb" as loaded
      And the data mart contains for "SKU-1001" on "wb" on 2026-10-11:
        | units |
        | 1     |
