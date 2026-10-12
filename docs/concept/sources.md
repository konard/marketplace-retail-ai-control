# Приложение: источники и проверка

Справочное приложение к [концепции](README.md), в лимит 2 страниц не входит.
Ссылки открыты и сверены 10.10.2026. Личного опыта внедрения описанных продуктов
у автора нет: всё, что ниже, опирается на документацию вендоров, их кейсы и одну
независимую проверку.

## Пример 1. Shopify Sidekick + Flow

| Утверждение в концепции | Источник | Тип |
|---|---|---|
| Sidekick собирает Flow (триггер, условия, действия), активация ручная, только десктоп, тарифы Basic/Shopify/Advanced/Plus | [Shopify Changelog, 11.12.2025](https://changelog.shopify.com/posts/create-flow-automations-with-sidekick) | вендор |
| Sidekick переводит вопросы в отчёты ShopifyQL | [Shopify Changelog](https://changelog.shopify.com/posts/turn-business-questions-into-analytics-reports-with-natural-language-queries) | вендор |
| SNOCKS: отчёты быстрее на 98% (≈30 минут → секунды), 4 отдела сами строят отчёты, руководитель e-commerce проверяет собранные Sidekick Flow и выпускает их в работу | [кейс SNOCKS](https://www.shopify.com/case-studies/snocks-sidekick) | кейс вендора |
| Flow: триггеры, условия, действия, расписание, складские сценарии; скриншот workflow | [страница Shopify Flow](https://www.shopify.com/flow) | вендор |
| Flow в Sidekick работают надёжно, KPI-анализы ненадёжны | тест tante-e: `https://tante-e.com/en/blogs/tante-e-blog/shopify-sidekick-test` | независимый тест |

## Пример 2. Битрикс24

| Утверждение в концепции | Источник | Тип |
|---|---|---|
| BI Конструктор работает на Apache Superset; скриншот дашборда | [справка 18897300](https://helpdesk.bitrix24.ru/open/18897300/) | вендор |
| Подключаются внешние MySQL, PostgreSQL и ClickHouse (в облаке — через серверное приложение Docker) | [справка 28344102](https://helpdesk.bitrix24.ru/open/28344102/) | вендор |
| Источники данных — CSV, рекламные кабинеты, базы 1С; объём данных ограничен тарифом для каждого источника | [справка 24355590](https://helpdesk.bitrix24.ru/open/24355590/) | вендор |
| Роботы ставят задачи, триггеры двигают сделку по стадиям | [справка 17784680](https://helpdesk.bitrix24.ru/open/17784680/), [справка 19427102](https://helpdesk.bitrix24.ru/open/19427102/) | вендор |
| BitrixGPT: задача с чек-листом, карточка CRM по звонку, итоги, MCP к 1С | [страница AI Битрикс24](https://www.bitrix24.ru/features/ai/) | вендор |
| REST-метод создания задачи | [`tasks.task.add`](https://apidocs.bitrix24.ru/api-reference/tasks/tasks-task-add.html) | вендор |

## Предлагаемый стек

| Компонент | Источник |
|---|---|
| Алерты Metabase (результат вопроса, цель) в email, Slack и webhook | [документация Metabase](https://www.metabase.com/docs/latest/questions/alerts) |
| Алерты и отчёты Superset (альтернатива) | [документация Superset](https://superset.apache.org/docs/configuration/alerts-reports/) |
| YandexGPT function calling | [Yandex Cloud](https://yandex.cloud/ru/docs/foundation-models/operations/yandexgpt/function-call) |

## Что не удалось проверить напрямую

- Документация API Wildberries и Ozon из среды проверки не открылась: ответы
  498 и 403 — антибот- или гео-заглушки. Поэтому ссылок на неё нет; набор
  данных (продажи, остатки, финансовые отчёты, реклама) надо уточнить на пилоте.
- Стандартный интерфейс OData в 1С (появился в платформе 8.3.5, нужна
  публикация на веб-сервере) подтверждён только сторонними статьями. Его
  наличие в конкретной конфигурации компании — открытый вопрос.
- Поддержку вызова функций в GigaChat видно по его SDK. Тариф и условия
  хранения данных надо уточнить у вендора.
- Тест tante-e открывается в браузере, но Cloudflare отвечает любому
  небраузерному клиенту ошибкой 429. Поэтому адрес дан текстом, а не ссылкой:
  иначе он ломает проверку ссылок в CI.
- Все цифры в сквозном сценарии условные и показывают только механику контура.
