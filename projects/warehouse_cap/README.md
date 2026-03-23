# warehouse_cap

Расчёт свободного места на складе по дням на основе:

- истории продаж,
- текущих остатков,
- запланированных поставок (PO).

Результат сохраняется в файл `out_warehouse_availiable_space.csv`.

## Зависимости

```bash
python -m pip install pandas scikit-learn
```

Запускайте скрипт из **этой** директории (рабочая папка — текущая).

## Входные файлы

В директории проекта должны лежать три CSV:

- `in_sales_by_<date>.csv` — история продаж по SKU.
- `in_inventory_level_on_<date>.csv` — стартовые остатки по SKU на дату расчёта.
- `in_supplied_products_by_<date>.csv` — планируемые поставки (PO).

`<date>` в имени файлов — формат `YYYY-MM-DD` (например, `2025-12-31`).

### `in_sales_by_<date>.csv`

Обязательные колонки:

- `Day` — дата продажи в формате `MM/DD/YYYY` (пример: `12/31/2025`).
- `Product variant SKU at time of sale` — идентификатор SKU.
- `Net items sold` — количество проданных единиц за запись (число).

Пример заголовка:

```csv
Day,Product variant SKU at time of sale,Net items sold
```

### `in_inventory_level_on_<date>.csv`

Обязательные колонки:

- `SKU` — идентификатор SKU.
- колонка с датой старта в формате `MM/DD/YYYY` (пример: `12/31/2025`) — стартовый остаток SKU на эту дату.

Дополнительно может быть служебная колонка индекса (например, пустая первая колонка из `pandas`), скрипт её не использует.

Пример заголовка:

```csv
,SKU,12/31/2025
```

### `in_supplied_products_by_<date>.csv`

Обязательные колонки:

- `Day` — дата поставки в формате `MM/DD/YYYY` (пример: `02/03/2026`).
- `SKU` — идентификатор SKU.
- `Qty` — количество поставки (число).

Дополнительно может быть служебная колонка индекса (например, пустая первая колонка из `pandas`), скрипт её не использует.

Пример заголовка:

```csv
,Day,SKU,Qty
```

## Запуск

```bash
python calculate_warehouse_available_cap.py <warehouse_capacity> <date_arg> <forecast_days_amount>
```

Параметры:

- `warehouse_capacity` — общее количество места на складе.
- `date_arg` — начальная дата расчёта в формате `YYYY-DD-MM` (внутри скрипта преобразуется в имена файлов и даты вида `YYYY-MM-DD` / `MM/DD/YYYY`).
- `forecast_days_amount` — горизонт прогноза в днях.

Пример:

```bash
python calculate_warehouse_available_cap.py 100000 2025-31-12 1096
```

## Выходной файл

- `out_warehouse_availiable_space.csv`

Таблица также выводится в консоль.
