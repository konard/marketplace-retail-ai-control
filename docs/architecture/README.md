# Architecture

This page shows how the pilot from the [concept](../concept/README.md) is
built: what we buy, what we write, how one morning runs and how a decision
moves from a proposal to a measured effect. The requirements are the
[Gherkin features](https://github.com/konard/marketplace-retail-ai-control/tree/main/features);
every scenario is an automated test.

The diagrams use one colour per kind of element:

```mermaid
flowchart LR
  classDef ext fill:#e8f1fb,stroke:#0b5394,color:#0b2a4a
  classDef ours fill:#ffffff,stroke:#1d6b2f,stroke-width:2px,color:#123d1c
  classDef data fill:#eaf5ec,stroke:#1d6b2f,color:#123d1c
  classDef ai fill:#fff4e5,stroke:#8a4b00,color:#4a2800
  classDef human fill:#f3e8fd,stroke:#6a1b9a,color:#3b0f57
  E["System we connect"]:::ext ~~~ O["Code we write"]:::ours ~~~ D[("Data we store")]:::data ~~~ A["AI model"]:::ai ~~~ H(["Person"]):::human
```

## 1. Context: the loop around the people who decide

The company keeps working in 1C and Bitrix24. The pilot adds one data mart,
alerts and an agent that turns a deviation into a proposal; people approve
and execute, and the system measures the result. Here the whole loop is one
box; the next section opens it.

```mermaid
flowchart LR
  classDef ext fill:#e8f1fb,stroke:#0b5394,color:#0b2a4a
  classDef ours fill:#ffffff,stroke:#1d6b2f,stroke-width:2px,color:#123d1c
  classDef ai fill:#fff4e5,stroke:#8a4b00,color:#4a2800
  classDef human fill:#f3e8fd,stroke:#6a1b9a,color:#3b0f57

  subgraph Sources["Sources"]
    WB["<b>Wildberries</b><br/>sales, ads, stock"]:::ext
    OZ["<b>Ozon</b><br/>sales, ads, stock"]:::ext
    C1["<b>1C</b><br/>cost price, SKU map"]:::ext
    AN["<b>Analytics service</b><br/>CSV export"]:::ext
  end

  SYS["<b>Management loop</b><br/>retail-ai-control,<br/>PostgreSQL, Metabase"]:::ours
  LLM["<b>LLM</b><br/>explains, proposes"]:::ai
  BX["<b>Bitrix24</b><br/>chat · tasks"]:::ext
  OWN(["<b>Owner, head of sales</b><br/>decide"]):::human
  MGR(["<b>Marketplace managers</b><br/>execute"]):::human

  Sources -->|"daily load"| SYS
  SYS <-->|"tools = SQL queries"| LLM
  SYS <-->|"digest, tasks ·<br/>task events"| BX
  SYS <-->|"card, journal ·<br/>approve, edit, reject"| OWN
  BX -->|"morning digest"| OWN
  BX -->|"task with checklist"| MGR

  style Sources fill:#f8fafc,stroke:#c8d1dc
```

## 2. Containers and modules

One Python package, `retail_ai_control`, runs as a scheduled CLI and as a web
app. Both use the same `Pilot` object, so a test drives exactly the code that
runs in production; external systems are replaced at the HTTP level with
`httpx.MockTransport`.

```mermaid
flowchart TB
  classDef ext fill:#e8f1fb,stroke:#0b5394,color:#0b2a4a
  classDef ours fill:#ffffff,stroke:#1d6b2f,stroke-width:2px,color:#123d1c
  classDef data fill:#eaf5ec,stroke:#1d6b2f,color:#123d1c
  classDef ai fill:#fff4e5,stroke:#8a4b00,color:#4a2800

  subgraph Entry["Entry points"]
    direction LR
    CLI["cli.py<br/>sync · morning · followup · ask · demo · serve"]:::ours
    WEB["web/app.py — FastAPI + Jinja + Pico CSS<br/>cards · journal · team · scorecard · webhooks"]:::ours
  end

  PILOT["pilot.py — Pilot: one object per run, wires settings to clients"]:::ours

  subgraph Steps["Steps of the loop"]
    direction LR
    SYNC["sync.py<br/>reconcile.py"]:::ours
    RULES["rules.py<br/>economics.py"]:::ours
    ANALYSIS["analysis.py<br/>queries.py"]:::ours
    AGENT["agent.py<br/>limits, numbers check"]:::ai
    DEC["decisions.py<br/>execution.py"]:::ours
    FU["followup.py<br/>metrics.py"]:::ours
    DIG["digest.py"]:::ours
  end

  subgraph Connectors["connectors/"]
    direction LR
    CWB["wildberries.py"]:::ext
    COZ["ozon.py"]:::ext
    C1C["onec.py — OData"]:::ext
    CCSV["analytics_csv.py"]:::ext
    CBX["bitrix24.py — REST webhook"]:::ext
  end

  MART[("mart.py — SQLAlchemy Core<br/>PostgreSQL in production, SQLite in tests")]:::data

  CLI --> PILOT
  WEB --> PILOT
  PILOT --> Steps
  SYNC --> CWB & COZ & C1C & CCSV
  DEC --> CBX
  DIG --> CBX
  FU --> CBX
  Steps --> MART

  style Entry fill:#f8fafc,stroke:#c8d1dc
  style Steps fill:#f6fbf7,stroke:#9cc5a6
  style Connectors fill:#f8fafc,stroke:#c8d1dc
```

| Layer | Ready library or service | Our code |
|---|---|---|
| HTTP clients | [httpx](https://www.python-httpx.org/) | five thin connectors, one file each |
| Storage | [SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/core/), PostgreSQL | table definitions and the unit-economics view |
| Dashboards and alerts | [Metabase](https://www.metabase.com/docs/latest/questions/alerts) | 10–15 saved questions |
| AI | any OpenAI-compatible API through the [openai](https://github.com/openai/openai-python) client: GigaChat, YandexGPT or a local model | tools, prompt, checks of numbers and limits |
| Web | [FastAPI](https://fastapi.tiangolo.com/), [Jinja](https://jinja.palletsprojects.com/), [Pico CSS](https://picocss.com/) | 6 server-rendered pages, no JavaScript |
| Tasks and chat | Bitrix24 REST: `tasks.task.add`, `im.message.add` | the task template |
| Specification | [pytest-bdd](https://pytest-bdd.readthedocs.io/) | step definitions in `tests/bdd/` |

## 3. One morning, step by step

`retail-ai-control morning` runs once a day from cron or a systemd timer.
Every step is idempotent: a failed source or a failed task is retried on the
next run and never stops the other steps.

```mermaid
sequenceDiagram
  autonumber
  participant S as Scheduler
  participant P as Pilot
  participant X as WB, Ozon, 1C, CSV
  participant D as Data mart
  participant L as LLM
  participant B as Bitrix24

  S->>P: morning
  rect rgb(232, 241, 251)
    P->>X: sync(last N days)
    X-->>P: sales, ads, stock, cost
    P->>D: replace the facts of the period
    P->>D: reconcile with the marketplace reports
  end
  rect rgb(234, 245, 236)
    P->>D: run_followups: decisions whose 7 days have passed
    D-->>P: margin before and after, control SKUs
    P->>B: comment on the task with the result
    P->>D: run_rules: margin, stock, sales, advertising
  end
  rect rgb(255, 244, 229)
    loop every open deviation without a proposal
      P->>D: evidence queries
      P->>L: explain and propose, tools = the queries
      L-->>P: cause, actions
      P->>P: check numbers and action limits
      P->>D: proposal with its evidence
    end
  end
  rect rgb(243, 232, 253)
    P->>B: retry_tasks for approved decisions without a task
    P->>B: send_digest — the 3–5 largest deviations
  end
```

If the model is not configured, unavailable or returns a number that is not
in the evidence, the proposal is built by the rules and labelled
«Расчёт по правилам»; the loop never waits for the AI.

## 4. The life of a decision

A decision is closed only when the follow-up shows that the goal was
achieved. Otherwise it stays in the journal as evaluated, the deviation is
reopened, and a new proposal links back to it with `parent_id`.

```mermaid
stateDiagram-v2
  classDef wait fill:#fff4e5,stroke:#8a4b00,color:#4a2800
  classDef work fill:#e8f1fb,stroke:#0b5394,color:#0b2a4a
  classDef good fill:#eaf5ec,stroke:#1d6b2f,color:#123d1c
  classDef off fill:#f1f1f1,stroke:#5c5c5c,color:#333333

  [*] --> proposed: deviation found
  proposed --> approved: approver, with edits
  proposed --> rejected: approver, with a reason
  rejected --> [*]: deviation dismissed
  approved --> in_progress: Bitrix24 task created
  note right of approved
    If Bitrix24 fails, the task
    is retried the next morning.
  end note
  in_progress --> done: task completed
  done --> evaluated: 7 days later, effect measured
  evaluated --> closed: goal achieved
  evaluated --> [*]: goal missed, new proposal with parent_id
  closed --> [*]

  class proposed wait
  class approved,in_progress,done work
  class evaluated wait
  class closed good
  class rejected off
```

| Status | Shown as | Who moves it |
|---|---|---|
| `proposed` | Ждёт решения | the agent or the rules |
| `approved` | Утверждено | an approver in the web app |
| `rejected` | Отклонено | an approver, a reason is required |
| `in progress` | В работе | the system, when the task is created |
| `done` | Выполнено, ждём эффект | Bitrix24 task event |
| `evaluated` | Цель не достигнута | follow-up, goal missed or partly achieved |
| `closed` | Цель достигнута | follow-up, goal achieved |

## 5. Data mart

All figures come from SQL over these tables; the AI reads them through the
same queries and cannot write.

```mermaid
erDiagram
  product ||--o{ cost_price : "priced from 1C"
  product ||--o{ sales_daily : "sold"
  product ||--o{ ad_spend_daily : "advertised"
  product ||--o{ stock_daily : "stocked"
  product ||--o{ deviation : "deviates"
  deviation ||--o{ evidence : "proved by"
  deviation ||--o{ decision : "answered by"
  decision ||--o{ decision_event : "journal"
  decision |o--o{ decision : "parent_id"

  product {
    string sku PK
    string wb_nm_id
    string ozon_sku
  }
  sales_daily {
    string channel PK
    string sku PK
    date day PK
    int units
    money revenue
    money commission
    money logistics
  }
  deviation {
    int id PK
    string rule
    string sku
    string channel
    money impact
    string status
  }
  evidence {
    int id PK
    string name
    text sql
    json rows
  }
  decision {
    int id PK
    int deviation_id FK
    int parent_id FK
    string status
    json actions
    string task_id
    string outcome
    money incremental_margin
  }
  decision_event {
    int id PK
    int decision_id FK
    string stage
    date on_day
  }
```

Support tables: `reconciliation` (computed vs reported revenue per channel and
week), `unmapped` (marketplace items without a 1C SKU) and `sync_run` (one row
per source and run). The view `unit_economics` adds the cost of goods and the
margin per SKU × channel × day.

## 6. Deployment

The proposed deployment for the pilot: one small virtual machine inside the
company network is enough for 30–50 SKUs. The tokens of the marketplaces and
Bitrix24 live only in the settings file on this machine.

```mermaid
flowchart TB
  classDef ext fill:#e8f1fb,stroke:#0b5394,color:#0b2a4a
  classDef ours fill:#ffffff,stroke:#1d6b2f,stroke-width:2px,color:#123d1c
  classDef data fill:#eaf5ec,stroke:#1d6b2f,color:#123d1c
  classDef ai fill:#fff4e5,stroke:#8a4b00,color:#4a2800
  classDef human fill:#f3e8fd,stroke:#6a1b9a,color:#3b0f57

  U(["<b>Browser</b><br/>owner, managers"]):::human

  subgraph VM["Company VM"]
    SSO["<b>Reverse proxy with SSO</b><br/>HTTPS, sets X-User-Id"]:::ext
    MB["<b>Metabase</b><br/>dashboards, alerts"]:::ext
    APP["<b>retail-ai-control</b><br/>serve: web app, webhooks<br/>morning: systemd timer"]:::ours
    PG[("<b>PostgreSQL</b><br/>data mart")]:::data
  end

  subgraph Outside["Internet, HTTPS"]
    LLM["<b>LLM API</b><br/>or a model on own GPU"]:::ai
    API["<b>WB · Ozon · 1C · Bitrix24</b><br/>REST, tokens in pilot.toml"]:::ext
  end

  U --> SSO --> APP
  MB -.->|"alert webhook"| APP
  APP -->|"facts, decisions"| PG
  MB -->|"SQL"| PG
  APP <-->|"load, tasks ·<br/>task events"| API
  APP -->|"explain, propose"| LLM

  style VM fill:#f6fbf7,stroke:#9cc5a6
  style Outside fill:#f8fafc,stroke:#c8d1dc
```

The settings are one TOML file (`pilot.toml`): tokens, the list of approvers,
the manager of each channel, margin plans and action limits. Run
`retail-ai-control demo` and `retail-ai-control serve --user 1` to see every
screen on demo data without connecting any system.
