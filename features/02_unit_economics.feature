@economics
Feature: Unit economics per SKU, channel and day
  As a marketplace manager
  I want the margin of every SKU after all marketplace costs
  So that I see which products actually earn money on which channel

  Rule: Margin = revenue - commission - logistics - advertising - units x unit cost

    Scenario Outline: Compute the margin of one SKU-day
      Given "SKU-1001" has a unit cost of <unit_cost> from 2026-09-01
      And "SKU-1001" sold on "ozon" on 2026-10-11:
        | units   | revenue   | commission   | logistics   | advertising   |
        | <units> | <revenue> | <commission> | <logistics> | <advertising> |
      When the unit economics of "SKU-1001" on "ozon" on 2026-10-11 are computed
      Then the margin is <margin> and the margin rate is <margin_pct>

      Examples: The end-to-end scenario before and after the bid increase
        | units | revenue | commission | logistics | advertising | unit_cost | margin  | margin_pct |
        | 10    | 8800.00 | 1320.00    | 880.00    | 792.00      | 440.00    | 1408.00 | 16.0%      |
        | 10    | 8800.00 | 1320.00    | 880.00    | 1848.00     | 440.00    | 352.00  | 4.0%       |

      Examples: Loss-making day
        | units | revenue | commission | logistics | advertising | unit_cost | margin  | margin_pct |
        | 2     | 1000.00 | 200.00     | 300.00    | 400.00      | 300.00    | -500.00 | -50.0%     |

    Scenario: The cost price valid on the sale date is used
      Given "SKU-1001" has a unit cost of 400.00 from 2026-09-01
      And "SKU-1001" has a unit cost of 440.00 from 2026-10-10
      And "SKU-1001" sold on "ozon" on 2026-10-09:
        | units | revenue | commission | logistics | advertising |
        | 1     | 880.00  | 0.00       | 0.00      | 0.00        |
      When the unit economics of "SKU-1001" on "ozon" on 2026-10-09 are computed
      Then the margin is 480.00 and the margin rate is 54.5%

    Scenario: A day without revenue has no margin rate
      Given "SKU-1001" has a unit cost of 440.00 from 2026-09-01
      And "SKU-1001" sold on "ozon" on 2026-10-11:
        | units | revenue | commission | logistics | advertising |
        | 0     | 0.00    | 0.00       | 50.00     | 100.00      |
      When the unit economics of "SKU-1001" on "ozon" on 2026-10-11 are computed
      Then the margin is -150.00 and the margin rate is not defined

  Rule: The margin is explained by cost items as shares of revenue

    Scenario: Break the margin down by cost item
      Given "SKU-1001" has a unit cost of 440.00 from 2026-09-01
      And "SKU-1001" sold on "ozon" on 2026-10-11:
        | units | revenue | commission | logistics | advertising |
        | 10    | 8800.00 | 1320.00    | 880.00    | 1848.00     |
      When the unit economics of "SKU-1001" on "ozon" on 2026-10-11 are computed
      Then the cost shares of revenue are:
        | item          | share |
        | commission    | 15.0% |
        | logistics     | 10.0% |
        | advertising   | 21.0% |
        | cost of goods | 50.0% |
        | margin        | 4.0%  |
