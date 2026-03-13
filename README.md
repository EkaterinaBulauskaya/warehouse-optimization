# calculate-warehouse-cap

Скрипт рассчитывает доступное место на складе по дням на основе:
- истории продаж,
- текущих остатков,
- запланированных поставок (PO).

Результат сохраняется в файл `warehouse_availiable_space.csv`.

## Установка зависимостей

```bash
python -m pip install pandas scikit-learn
```

## Формат входных файлов

В рабочей директории должны быть CSV-файлы:
- `sales_by_<date>.csv`
- `inventory_level_on_<date>.csv`
- `supplied_products_by_<date>.csv`

Где `<date>` — дата в формате `YYYY-MM-DD` после внутреннего преобразования скрипта.

## Запуск

```bash
python calculate_warehouse_available_cap.py <warehouse_capacity> <date_arg>
```

Пример:

```bash
python calculate_warehouse_available_cap.py 100000 2025-31-12
```

`<date_arg>` ожидается в формате `YYYY-DD-MM`, например `2025-31-12`, и внутри скрипта преобразуется в `2025-12-31`.

## Выходной файл

После запуска создается:
- `warehouse_availiable_space.csv`

Также таблица печатается в консоль.
