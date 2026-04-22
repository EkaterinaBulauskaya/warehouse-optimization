# order_recommendations

Рекомендации по заказам SKU с учетом:

- ABC/XYZ-категории товара,
- прогноза продаж,
- окна свежести,
- MOQ,
- доступной емкости склада по дням.

Результат сохраняется в `out/out_order_recommendations.csv`.

## Входные файлы

Скрипт запускается из корня репозитория и использует единый каталог `in/`.

Обязательные входные CSV:

- `in/in_sales_by_<in_file_date>.csv` - история продаж.
- `in/in_inventory_level_on_<in_file_date>.csv` - остатки на стартовую дату.
- `in/in_supplied_products_by_<in_file_date>.csv` - поставки (PO).
- `in/in_products_for_pallet.csv` - количество единиц в паллете.
- `in/in_for_abc_xyz_analysis.csv` - данные для ABC/XYZ.
- `in/in_products_MOQ.csv` - минимальная партия заказа по SKU.
- `in/in_freshness_window_data.csv` - окно свежести по SKU.

`<in_file_date>`: формат `YYYY-MM-DD` (например, `2025-12-31`).

Обязательные колонки (по файлам):

- `in/in_sales_by_<in_file_date>.csv`: `Day`, `Product variant SKU at time of sale`, `Net items sold`.
- `in/in_inventory_level_on_<in_file_date>.csv`: `SKU` и колонка стартовой даты (`MM/DD/YYYY`) с остатком.
- `in/in_supplied_products_by_<in_file_date>.csv`: `Day`, `SKU`, `Qty`.
- `in/in_products_for_pallet.csv`: `SKU`, `Units per pallet`.
- `in/in_for_abc_xyz_analysis.csv`: `Day`, `SKU`, `Sold`, `Price`, `Cost`, `Status`.
- `in/in_products_MOQ.csv`: `SKU`, `MOQ`.
- `in/in_freshness_window_data.csv`: `SKU`, `Freshness_window`.

## Запуск

```bash
python make_order_recommendations.py <warehouse_capacity> <in_file_date> <forecast_days_amount>
```

Параметры:

- `warehouse_capacity` - общая емкость склада в паллетах.
- `in_file_date` - дата в формате `YYYY-DD-MM` (как и в `calculate_warehouse_available_cap.py`).
- `forecast_days_amount` - горизонт прогноза в днях.

Пример: `python make_order_recommendations.py 500 2025-31-12 365`

## Выходной файл

- `out/out_order_recommendations.csv`

Таблица также печатается в консоль.

## Тесты

Отдельных тестов для `make_order_recommendations.py` пока нет. Проверка:

```bash
python -m pytest -v
```
