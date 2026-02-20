# mpp-core

Modular MVP-core for marketplace pipeline:
`1688 ingestion -> compliance -> category/attribute mapping -> AI enrichment -> Ozon export`

Проект на этапе архитектурного каркаса. Бизнес-правила, реальные API-интеграции и продовые адаптеры пока не реализованы.

## 1. Общее описание проекта

`mpp-core` — монолитный модульный backend-ядро для обработки товарных карточек между маркетплейсами.

Цели MVP-основы:
- зафиксировать доменную модель и этапы пайплайна;
- изолировать внешние интеграции через интерфейсы;
- обеспечить простую замену заглушек на реальные адаптеры;
- сохранить минимальную связанность между слоями.

Ограничения текущей версии:
- без реального парсинга 1688;
- без реальных HTTP/API вызовов;
- без асинхронности, очередей и микросервисов;
- без бизнес-логики (только каркас и контракты).

## 2. Архитектура и структура модулей

```text
mpp_core/
  config/
    settings.py               # централизованная env-конфигурация

  domain/
    enums.py                  # PipelineStage, ProductStatus
    models.py                 # Product, SKU, Category, Attribute

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

  enrichment/
    interfaces.py             # BaseAIProvider, ImageProcessor
    service.py                # EnrichmentService
    stubs.py                  # StubAIProvider, NoOpImageProcessor

  export/
    base.py                   # BaseMarketplaceExporter
    payload.py                # PayloadBuilder, OzonPayloadBuilder
    ozon.py                   # OzonExporter (stub)
    models.py                 # ExportResult

  storage/
    repositories.py           # ProductRepository, PipelineEventRepository
    in_memory.py              # in-memory реализации + mapping stores

  pipeline/
    orchestrator.py           # PipelineOrchestrator (линейный пайплайн)

main.py                       # пример запуска на заглушках
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
- демонстрационный запуск в `main.py`.

Проверка:
- `python3 -m compileall -q mpp_core main.py`
- `python3 main.py`

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
python3 main.py
```

Ожидаемый результат (пример):
```text
Processed products: 1
- 1688-1001 | status=exported | stage=export | export_id=ozon-1688-1001
```
