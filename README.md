# mpp-core

Modular MVP-core for marketplace pipeline:
`1688 ingestion -> compliance -> category/attribute mapping -> AI enrichment -> Ozon export`

Проект на этапе рабочего MVP-каркаса.
Сейчас доступны два практических контура:
- Ozon import-сценарии (`ozon-mvp`, `ozon-json-import`);
- TMAPI ingestion из 1688 (`tmapi-test`) с сохранением результатов одновременно в JSON и SQLite.

## 1. Общее описание проекта

`mpp-core` — монолитный модульный backend-ядро для обработки товарных карточек между маркетплейсами.

Цели текущего этапа:
- зафиксировать доменную модель и этапы пайплайна;
- изолировать внешние интеграции через интерфейсы и адаптеры;
- держать инфраструктурные зависимости (API, storage) вне бизнес-логики;
- подготовить базу для перехода к полноценному ingestion->pipeline циклу.

Ограничения текущей версии:
- основной `PipelineOrchestrator` все еще демонстрационный (stub ingestion/export внутри pipeline-run);
- без асинхронности, очередей и микросервисов;
- без production-grade rule engine и полноценных mapping-management интерфейсов.

## 2. Архитектура и структура модулей

```text
mpp_core/
  config/
    settings.py               # централизованная env-конфигурация

  domain/
    enums.py                  # PipelineStage, ProductStatus
    models.py                 # Product, SKU, Category, Attribute
    internal_product.py       # universal internal product model for JSON import

  ingestion/
    base.py                   # BaseIngestionClient
    dto.py                    # RawProductDTO, RawSKU, Raw1688Product
    alibaba_1688.py           # Alibaba1688Client (stub for orchestrator demo)
    tmapi_1688_client.py      # TMAPI HTTP client (real requests)
    tmapi_1688_ingestion.py   # TMAPI ingestion flow + JSON artifacts

  compliance/
    rules.py                  # ComplianceRule + stub-rule
    models.py                 # ComplianceCheckResult
    engine.py                 # ComplianceEngine

  mapping/
    interfaces.py             # абстракции хранения маппинга
    mappers.py                # CategoryMapper, AttributeMapper
    json_mapping_loader.py    # загрузка mapping.json и lookup по category

  enrichment/
    interfaces.py             # BaseAIProvider, ImageProcessor
    service.py                # EnrichmentService
    stubs.py                  # StubAIProvider, NoOpImageProcessor

  export/
    base.py                   # BaseMarketplaceExporter
    payload.py                # PayloadBuilder, OzonPayloadBuilder
    json_payload_builder.py   # internal product -> mapped payload item
    json_import_runner.py     # products.json -> Ozon import/info
    ozon.py                   # OzonExporter (stub)
    ozon_api_client.py        # OzonApiClient (real HTTP client)
    ozon_mvp.py               # E2E import flow: category->attributes->import->status
    models.py                 # ExportResult

  storage/
    repositories.py           # ProductRepository, PipelineEventRepository
    in_memory.py              # in-memory реализации + mapping stores
    sqlite/
      database.py             # sqlite connection + first-run schema apply
      schema.sql              # products table schema
      models.py               # ProductRecord dataclass
      product_repository.py   # SqliteProductRepository

  pipeline/
    orchestrator.py           # PipelineOrchestrator (линейный пайплайн)

main.py                       # CLI-runner сценарии

data/
  products.json               # тестовые internal товары (JSON import)
  mapping.json                # category/attribute mapping (internal -> Ozon)
  1688_products_raw.json      # raw результат TMAPI ingestion
  mpp_core.db                 # SQLite база (создается автоматически)
```

### Зависимости между слоями
- `domain` — центральный слой, не зависит от остальных.
- `ingestion`, `compliance`, `mapping`, `enrichment`, `export`, `storage` зависят от `domain`.
- `pipeline` оркестрирует все модули и управляет стадиями/статусами.
- База данных подключается через storage-adapter (`storage/sqlite`) и не смешивается с доменной логикой.

## 3. Текущий статус реализации

Реализовано:
- базовая модульная структура репозитория;
- доменные сущности и enum-статусы пайплайна;
- интерфейсы и stub-реализации для демонстрационного pipeline;
- линейный `PipelineOrchestrator` с управлением стадиями/статусами;
- загрузка конфигурации из `.env` / `.env.local`;
- реальный Ozon API-клиент и рабочие сценарии `ozon-mvp`, `ozon-json-import`;
- TMAPI клиент и рабочий ingestion-сценарий `tmapi-test`;
- persistency layer на SQLite (`data/mpp_core.db`) для хранения 1688 продуктов;
- repository pattern для SQLite (`SqliteProductRepository`);
- upsert логика по уникальному `item_id_1688` для дедупликации входящих товаров;
- test-scenario `sqlite-test` для проверки БД-слоя;
- логирование API-артефактов в `logs/1688` и `logs/ozon`.

Проверка (базовая):
- `python3 -m compileall -q mpp_core main.py`
- `python3 main.py`
- `python3 main.py ozon-mvp`
- `python3 main.py ozon-json-import`
- `python3 main.py tmapi-test`
- `python3 main.py sqlite-test`

## 4. Актуальные сценарии запуска

1. Demo pipeline (stub ingestion + in-memory storage):
```bash
python3 main.py
```

2. Ozon MVP import (1 тестовый товар через dynamic category flow):
```bash
python3 main.py ozon-mvp
```

3. Ozon JSON import (`data/products.json` + `data/mapping.json`):
```bash
python3 main.py ozon-json-import
```

4. TMAPI 1688 ingestion:
- тянет товары из TMAPI;
- сохраняет raw JSON в `data/1688_products_raw.json`;
- upsert-ит товары в SQLite (`data/mpp_core.db`, таблица `products`) с уникальностью по `item_id_1688`.

```bash
python3 main.py tmapi-test
```

5. SQLite smoke test:
```bash
python3 main.py sqlite-test
```

## 5. Принятые архитектурные решения

1. Монолитный модульный подход (без микросервисов) для ускорения MVP.
2. Domain-centric структура: `domain` — единый источник внутренних моделей.
3. Порты и адаптеры: внешние системы доступны через интерфейсы/адаптеры.
4. Конструкторная инъекция зависимостей для явного и тестируемого wiring.
5. Линейный orchestration flow в одном месте (`PipelineOrchestrator`).
6. In-memory адаптеры сохраняются для быстрого локального prototyping.
7. Для раннеров ingestion введен отдельный SQLite storage-адаптер без изменения in-memory pipeline.

## 6. Changelog

### 2026-03-04
- Добавлен SQLite storage слой: `mpp_core/storage/sqlite/`.
- Добавлен `schema.sql` с таблицей `products` и `UNIQUE(item_id_1688)`.
- Добавлен `ProductRecord` и `SqliteProductRepository` (CRUD + status/category/translation updates).
- Добавлен env-параметр `MPP_SQLITE_DB_PATH` (дефолт `data/mpp_core.db`).
- Добавлен CLI-сценарий `python3 main.py sqlite-test`.
- `tmapi-test` теперь сохраняет ingestion-результат не только в JSON, но и в SQLite.
- Добавлен upsert для 1688 товаров по `item_id_1688` с дедупликацией повторных запусков.

### 2026-02-24
- Добавлена загрузка переменных из `.env` и `.env.local` в `Settings`.
- Добавлены env-параметры `MPP_OZON_SELLER_CLIENT_ID` и `MPP_OZON_SELLER_API_KEY`.
- Ozon exporter получает credentials из конфигурации приложения.
- Добавлен шаблон `.env.example`.
- Добавлен `OzonApiClient` с реальными POST-запросами и auth headers (`Client-Id`, `Api-Key`).
- Добавлен MVP-runner реального импорта товара в Ozon: категории, обязательные атрибуты, dictionary values, `product/import`, `product/import/info`.
- Добавлено логирование всех request/response в `logs/ozon/`.
- Добавлен JSON pipeline импорта товаров в Ozon: `data/products.json` -> `data/mapping.json` -> payload -> `/v3/product/import`.
- Добавлены `JsonMappingLoader`, `JsonPayloadBuilder`, `OzonJsonImportRunner`.
- Добавлены логи JSON-import: `logs/ozon/json_request.json`, `logs/ozon/json_response.json`.

### 2026-02-20
- Инициализирована архитектурная основа `mpp-core`.
- Добавлены модули: `ingestion`, `domain`, `compliance`, `mapping`, `enrichment`, `export`, `storage`, `pipeline`, `config`.
- Добавлены интерфейсы и stub-реализации без production бизнес-логики.
- Добавлен пример запуска пайплайна на заглушках (`main.py`).

## 7. Roadmap

1. `v0.2` — Интеграция TMAPI ingestion с основным pipeline (`PipelineOrchestrator`) через устойчивые contracts.
2. `v0.3` — Реальные compliance rules и конфигурация наборов правил.
3. `v0.4` — Production-ready mapping management (источник mapping не только JSON).
4. `v0.5` — Расширение SQLite слоя (pagination/filtering, migrations, транзакционные batch-операции).
5. `v0.6` — Реальный AI provider adapter + quality controls.
6. `v0.7` — Production Ozon export adapter с управлением retry/error policy.

## 8. Правила дальнейшего расширения проекта

1. Любая новая внешняя интеграция добавляется через новый интерфейс + адаптер.
2. Бизнес-логика не добавляется в инфраструктурные слои (`storage`, `export`, `ingestion`).
3. Все новые статусы/стадии фиксируются в `domain/enums.py`.
4. Новые use-case сценарии должны входить через `pipeline` или отдельный orchestration сервис.
5. При изменениях архитектуры обязателен апдейт разделов `Архитектура`, `Текущий статус`, `Changelog`, `Roadmap` в README.
6. При добавлении production-логики сохраняется обратная совместимость интерфейсов либо делается версия контракта.

## 9. Быстрый старт

```bash
cp .env.example .env
python3 -m compileall -q mpp_core main.py
```

### Обязательные env-параметры

Ozon-сценарии:
- `MPP_OZON_SELLER_CLIENT_ID`
- `MPP_OZON_SELLER_API_KEY`

TMAPI ingestion:
- `MPP_TMAPI_TOKEN`

SQLite storage:
- `MPP_SQLITE_DB_PATH` (по умолчанию `data/mpp_core.db`)

Дополнительно:
- `MPP_OZON_SELLER_BASE_URL`, `MPP_OZON_VERIFY_SSL`, `MPP_OZON_REQUEST_TIMEOUT_SEC`
- `MPP_TMAPI_BASE_URL`, `MPP_TMAPI_TIMEOUT_SEC`, `MPP_TMAPI_VERIFY_SSL`
- `MPP_TMAPI_MODE`, `MPP_TMAPI_CAT_IDS`, `MPP_TMAPI_CATEGORY_PAGES`, `MPP_TMAPI_TOP_LIMIT`, `MPP_TMAPI_SHOP_URL`, `MPP_TMAPI_MEMBER_ID`

## 10. Детали ключевых раннеров

### 10.1 `ozon-json-import`

Назначение:
- simple bridge для импорта internal JSON-товаров в Ozon.

Вход:
- `data/products.json`
- `data/mapping.json`

Выход:
- `logs/ozon/json_request.json`
- `logs/ozon/json_response.json`

### 10.2 `tmapi-test` (1688 + SQLite)

Что делает:
- получает товары из TMAPI (`top_sales` или `shop` режим);
- пишет raw-данные в `data/1688_products_raw.json`;
- upsert-ит товары в таблицу `products` в SQLite;
- уникальность определяется по `item_id_1688`.

Статус новых записей:
- `new`

Поддерживаемые pipeline-статусы в SQLite:
- `new`
- `translated`
- `mapped`
- `ready_for_export`
- `exported`

Проверка после запуска:
```bash
python3 main.py tmapi-test
sqlite3 data/mpp_core.db ".tables"
sqlite3 data/mpp_core.db "SELECT item_id_1688,status FROM products ORDER BY id DESC LIMIT 20;"
```

### 10.3 `sqlite-test`

Smoke-проверка SQLite слоя:
- создаёт БД и схему;
- добавляет тестовый товар;
- читает его обратно;
- печатает результат в консоль.
