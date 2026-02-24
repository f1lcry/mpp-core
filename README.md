# mpp-core

Modular MVP-core for marketplace pipeline:
`1688 ingestion -> compliance -> category/attribute mapping -> AI enrichment -> Ozon export`

Проект на этапе архитектурного каркаса. Основной pipeline все еще работает на заглушках, но добавлены рабочие Ozon-сценарии:
- `ozon-mvp` — импорт 1 тестового товара через динамический подбор категории/атрибутов;
- `ozon-json-import` — импорт массива товаров из `data/products.json` через локальный mapping `data/mapping.json`.

## 1. Общее описание проекта

`mpp-core` — монолитный модульный backend-ядро для обработки товарных карточек между маркетплейсами.

Цели MVP-основы:
- зафиксировать доменную модель и этапы пайплайна;
- изолировать внешние интеграции через интерфейсы;
- обеспечить простую замену заглушек на реальные адаптеры;
- сохранить минимальную связанность между слоями.

Ограничения текущей версии:
- без реального парсинга 1688;
- без асинхронности, очередей и микросервисов;
- без полноценной бизнес-логики (кроме минимального Ozon import flow).

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
    dto.py                    # RawProductDTO, RawSKU
    alibaba_1688.py           # Alibaba1688Client (stub)

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

  pipeline/
    orchestrator.py           # PipelineOrchestrator (линейный пайплайн)

main.py                       # пример запуска на заглушках
data/
  products.json               # тестовые internal товары (JSON only)
  mapping.json                # category/attribute mapping (internal -> Ozon)
```

### Зависимости между слоями
- `domain` — центральный слой, не зависит от остальных.
- `ingestion`, `compliance`, `mapping`, `enrichment`, `export`, `storage` зависят от `domain`.
- `pipeline` оркестрирует все модули и управляет стадиями/статусами.
- Внешние интеграции подключаются только через абстракции (`ABC` интерфейсы).

## 3. Текущий статус реализации

Реализовано:
- базовая модульная структура репозитория;
- доменные сущности и enum-статусы пайплайна;
- интерфейсы и заглушки для всех целевых модулей;
- линейный `PipelineOrchestrator` с управлением статусами продукта;
- constructor-based dependency injection;
- in-memory storage адаптеры для локального запуска;
- демонстрационный запуск в `main.py`;
- загрузка конфигурации из `.env` / `.env.local` с прокидкой Ozon Seller API ключей в экспортёр.
- рабочий сценарий `python3 main.py ozon-mvp` для импорта 1 тестового товара в Ozon Seller API;
- логирование всех запросов/ответов в `logs/ozon/request.json` и `logs/ozon/response.json`.
- рабочий сценарий `python3 main.py ozon-json-import` для импорта товаров из `data/products.json`;
- отдельные логи JSON-import в `logs/ozon/json_request.json` и `logs/ozon/json_response.json`.

Проверка:
- `python3 -m compileall -q mpp_core main.py`
- `python3 main.py`
- `python3 main.py ozon-mvp`
- `python3 main.py ozon-json-import`

## 4. Планируемые модули и фичи

Ближайшие этапы:
- подключение реального клиента ingestion для 1688;
- реализация реальных compliance-правил;
- реализация постоянного хранилища (PostgreSQL + repository adapters);
- реализация production payload/export для Ozon API;
- реализация настраиваемых mapping-таблиц;
- расширение AI enrichment (описания, теги, image pipeline).

## 5. Принятые архитектурные решения

1. Монолитный модульный подход (без микросервисов) для ускорения MVP.
2. Domain-centric структура: `domain` — единый источник внутренних моделей.
3. Порты и адаптеры: внешние системы доступны только через интерфейсы.
4. Конструкторная инъекция зависимостей для явного и тестируемого wiring.
5. Линейный orchestration flow в одном месте (`PipelineOrchestrator`).
6. In-memory адаптеры как временные реализации для локального prototyping.

## 6. Changelog

### 2026-02-24
- Добавлена загрузка переменных из `.env` и `.env.local` в `Settings`.
- Добавлены env-параметры `MPP_OZON_SELLER_CLIENT_ID` и `MPP_OZON_SELLER_API_KEY`.
- Ozon exporter теперь получает Ozon Seller credentials из конфигурации приложения.
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
- Добавлены интерфейсы и stub-реализации без бизнес-логики.
- Добавлен пример запуска пайплайна на заглушках (`main.py`).
- README переведен в формат актуального проектного документа.

## 7. Roadmap

1. `v0.2` — Persistency layer (DB repositories, migrations).
2. `v0.3` — Реальные rules в compliance и конфигурация наборов правил.
3. `v0.4` — Production-ready mapping management.
4. `v0.5` — Реальный Ozon export adapter + error handling.
5. `v0.6` — Реальный AI provider adapter + quality controls.

## 8. Правила дальнейшего расширения проекта

1. Любая новая внешняя интеграция добавляется через новый интерфейс + адаптер, без прямых вызовов из `pipeline`.
2. Бизнес-логика не добавляется в инфраструктурные слои (`storage`, `export`, `ingestion`).
3. Все новые статусы/стадии фиксируются в `domain/enums.py`.
4. Новые use-case сценарии должны входить через `pipeline` или отдельный orchestration сервис.
5. При изменениях архитектуры обязателен апдейт разделов `Архитектура`, `Текущий статус`, `Changelog`, `Roadmap` в README.
6. При добавлении production-логики сохраняется обратная совместимость интерфейсов либо делается версия контракта.

## 9. Быстрый старт

```bash
cp .env.example .env
python3 main.py
```

Реальный Ozon MVP-сценарий (1 тестовый товар):
```bash
python3 main.py ozon-mvp
```

JSON import в Ozon (товары из `data/products.json`):
```bash
python3 main.py ozon-json-import
```

Переменные для Ozon Seller API (в `.env`):
- `MPP_OZON_SELLER_CLIENT_ID`
- `MPP_OZON_SELLER_API_KEY`
- `MPP_OZON_SELLER_BASE_URL` (по умолчанию `https://api-seller.ozon.ru`)
- `MPP_OZON_VERIFY_SSL` (`true`/`false`)
- `MPP_OZON_REQUEST_TIMEOUT_SEC`

Ожидаемый результат (пример):
```text
Processed products: 1
- 1688-1001 | status=exported | stage=export | export_id=ozon-1688-1001
```

## 10. JSON Import MVP (`ozon-json-import`)

Этот слой нужен как простой bridge перед будущим ingestion из 1688 и AI enrichment:
- вход только из JSON (`data/products.json`);
- mapping только из JSON (`data/mapping.json`);
- без БД и без сложной бизнес-логики.

### 10.1 Формат `data/products.json`

```json
[
  {
    "category": "tape_measure",
    "title": "Рулетка 5м",
    "description": "Строительная рулетка",
    "price": 500,
    "attributes": {
      "brand": "NoName",
      "length": "5m",
      "color": "black"
    },
    "images": ["https://example.com/image.jpg"]
  }
]
```

### 10.2 Формат `data/mapping.json`

```json
{
  "tape_measure": {
    "category_id": 17028629,
    "type_id": 91705,
    "attributes": {
      "brand": 85,
      "model": 9048,
      "type": 8229
    },
    "required_attributes": ["brand", "model", "type"],
    "default_values": {
      "brand": "Юпитер",
      "type": "Измерительная рулетка"
    }
  }
}
```

### 10.3 Что делает runner

- читает `products.json`;
- для каждого товара берет mapping по `category`;
- валидирует обязательные атрибуты;
- собирает payload items;
- отправляет `/v3/product/import`;
- вызывает `/v1/product/import/info` (poll до финального статуса);
- проверяет, что все items имеют статус `imported` и без `errors`;
- сохраняет request/response в:
  - `logs/ozon/json_request.json`
  - `logs/ozon/json_response.json`
