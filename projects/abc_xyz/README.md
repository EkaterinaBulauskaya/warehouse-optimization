# abc_xyz

ABC/XYZ-анализ ассортимента: категории по маржинальности (ABC) и по стабильности спроса (XYZ). Итог — матрица категорий по SKU.

Результат сохраняется в файл `out_abc_xyz_analysis_results.csv`.

## Зависимости

```bash
python -m pip install pandas scikit-learn
```

Запускайте скрипт из **этой** директории (рабочая папка — текущая).

## Входные файлы

В директории проекта должен лежать:

- `in_for_abc_xyz_analysis.csv` — построчная история по SKU.

Ожидаемые колонки (как в коде скрипта):

- `Day` — дата (парсится как дата/время).
- `SKU` — идентификатор товара.
- `Sold` — продажи за строку.
- `Price`, `Cost` — цена и себестоимость (для маржи в ABC).
- `Status` — признак наличия на складе (`1` / `0`); для строк с `0` при необходимости дозаполняются продажи.
- Служебные колонки `Unnamed:*` (индекс при экспорте из pandas) при чтении **отбрасываются**.

Минимум **90** дней истории по SKU, иначе SKU не попадает в расчёт.

## Запуск

```bash
python get_product_abc_xyz_analysis.py
```

## Тесты

Автотесты: [`tests/test_get_product_abc_xyz_analysis.py`](tests/test_get_product_abc_xyz_analysis.py) (в т.ч. регрессия `repair_product` — `test_repair_product_handles_missing_status_without_indexing_error`).

**Рекомендуется** запускать из **корня репозитория** (так подхватывается [`pytest.ini`](../../pytest.ini)):

```bash
python -m pip install -r ../../requirements-dev.txt
python -m pytest projects/abc_xyz/tests -v
```

Полный прогон всех тестов обоих проектов:

```bash
python -m pytest -v
```

## Выходной файл

- `out_abc_xyz_analysis_results.csv`

Таблица также выводится в консоль.
