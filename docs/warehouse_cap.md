# warehouse_cap

Расчёт свободного места на складе в паллетах по дням на основе:

- истории продаж,
- текущих остатков,
- запланированных поставок (PO).

Результат сохраняется в файл `out/out_warehouse_available_space.csv`.

## Входные файлы

Скрипт читает CSV из `in/`:

- `in/in_sales_by_<in_file_date>.csv`
- `in/in_products_for_pallet.csv`
- `in/in_inventory_level_on_<in_file_date>.csv`
- `in/in_supplied_products.csv`

`<in_file_date>`: формат `YYYY-MM-DD` (например, `2025-12-31`).

Обязательные колонки:

- `in/in_sales_by_<in_file_date>.csv`: `Day`, `Product variant SKU at time of sale`, `Net items sold`.
- `in/in_products_for_pallet.csv`: `SKU`, `Units per pallet`.
- `in/in_inventory_level_on_<in_file_date>.csv`: `SKU` и колонка даты в формате `MM/DD/YYYY` (например `12/31/2025`) со стартовым остатком.
- `in/in_supplied_products.csv`: `Day`, `SKU`, `Qty`.

## Запуск

```bash
python calculate_warehouse_available_cap.py <warehouse_capacity> <in_file_date> <forecast_days_amount>
```

Параметры:

- `warehouse_capacity` — общее количество места на складе (в паллетах).
- `in_file_date` — начальная дата расчёта в формате `YYYY-DD-MM` (внутри скрипта преобразуется в имена файлов и даты вида `YYYY-MM-DD` / `MM/DD/YYYY`).
- `forecast_days_amount` — горизонт прогноза в днях.

Пример: `python calculate_warehouse_available_cap.py 500 2025-31-12 1096`

## Выходной файл

- `out/out_warehouse_available_space.csv`

Таблица также выводится в консоль.

## Тесты

```bash
python -m pytest -v
```
