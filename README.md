# Example of warehouse optimization

[![CI (tests)](https://github.com/EkaterinaBulauskaya/warehouse-optimization/actions/workflows/warehouse-optimization-ci.yml/badge.svg)](https://github.com/EkaterinaBulauskaya/warehouse-optimization/actions/workflows/warehouse-optimization-ci.yml)

Репозиторий с тремя Python-скриптами для оптимизации склада. Скрипты запускаются из корня, входные данные лежат в `in/`, результаты
сохраняются в `out/`.

| Проект                                 | Описание                                                                       | Документация                            |
|----------------------------------------|--------------------------------------------------------------------------------|-----------------------------------------|
| `calculate_warehouse_available_cap.py` | Прогноз и расчёт **свободного места на складе** по дням (продажи, остатки, PO) | [README](docs/warehouse_cap.md)         |
| `get_product_abc_xyz_analysis.py`      | **ABC/XYZ-анализ** ассортимента по SKU                                         | [README](docs/abc_xyz.md)               |
| `make_order_recommendations.py`        | Рекомендации по заказам с учётом ABC/XYZ, оборачиваемости и ёмкости склада     | [README](docs/order_recommendations.md) |

## Общие зависимости

Установка зависимостей:

```bash
python -m pip install -r requirements-dev.txt
```

## Структура репозитория

```text
calculate_warehouse_available_cap.py
get_product_abc_xyz_analysis.py
make_order_recommendations.py
in/                  # общие входные CSV
out/                 # общие выходные CSV
tests/               # общие автотесты
docs/                # проектные README
*.ipynb              # ноутбуки анализов
```

Подробности по форматам данных и запуску — в README соответствующих модулей в папке [docs](docs).

## Тесты

```bash
python -m pytest -v
```
