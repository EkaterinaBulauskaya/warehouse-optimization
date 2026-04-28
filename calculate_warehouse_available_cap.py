import sys, math
from datetime import timedelta

import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

INPUT_INVENTORY_LEVEL_FILENAME = 'in/in_inventory_level_on_{}.csv'
INPUT_SALES_FILENAME = 'in/in_sales_by_{}.csv'
INPUT_SUPPLIED_PRODUCTS_FILENAME = 'in/in_supplied_products_by_{}.csv'
INPUT_PALLETS_FILENAME = 'in/in_products_for_pallet.csv'
MIN_HISTORY_DAYS = 90  # Минимум дней истории продаж для участия SKU в прогнозе.
OUTPUT_FILENAME = 'out/out_warehouse_available_space.csv'  # Имя CSV-файла с результатом расчета.


def parse_args():
    '''Читает аргументы CLI и нормализует дату для имен входных файлов.'''
    if len(sys.argv) != 4:
        raise ValueError('Usage: python calculate_warehouse_available_cap.py <warehouse_capacity> <in_file_date> <forecast_days_amount>')
    warehouse_capacity = int(sys.argv[1])
    raw_date = sys.argv[2]
    normalized_date = raw_date[:4] + '-' + raw_date[8:10] + '-' + raw_date[5:7]
    forecast_days_amount = int(sys.argv[3])
    return warehouse_capacity, normalized_date, forecast_days_amount


def fill_missing_dates(df):
    '''Заполняет пропущенные дни в диапазоне дат нулевыми продажами.'''
    df['Day'] = pd.to_datetime(df['Day'], errors='coerce')
    full_range = pd.date_range(start=df['Day'].min(), end=df['Day'].max(), freq='D')
    df = df.set_index('Day').reindex(full_range, fill_value=0)
    return df.rename_axis('Day').reset_index()


def predict_sales(days_ahead, sales_df, source_col='Sold', result_col='Predicted Sold'):
    '''Строит линейный прогноз продаж на заданное количество дней вперед.'''
    model = LinearRegression()
    model.fit(sales_df[['Date_ordinal']], sales_df[source_col])

    last_date = sales_df['Day'].max()
    future_dates = [pd.to_datetime(last_date) + timedelta(days=i) for i in range(1, days_ahead + 1)]
    future_ordinals = [day.toordinal() for day in future_dates]

    predicted_values = model.predict(pd.DataFrame({'Date_ordinal': future_ordinals}))
    predicted_values = [float(x) if float(x) >= 0 else 0 for x in predicted_values]
    return pd.DataFrame({'Day': future_dates, result_col: predicted_values})


def aggregate_sku_sales(sku_df):
    '''Агрегирует продажи SKU по дням и добавляет порядковый номер даты.'''
    sku_df = sku_df.sort_values(['Day'], ascending=False)
    daily_sales = sku_df.groupby('Day', as_index=False)['Net items sold'].sum()
    daily_sales = daily_sales.rename(columns={'Net items sold': 'Sold'})
    daily_sales = fill_missing_dates(daily_sales)
    daily_sales['Date_ordinal'] = daily_sales['Day'].map(pd.Timestamp.toordinal)
    return daily_sales


def prepare_products(filename):
    '''Готовит датасеты по SKU и оставляет только SKU с достаточной историей.'''
    data = pd.read_csv(filename)
    data['Day'] = pd.to_datetime(data['Day'])

    sku_list = list(data['Product variant SKU at time of sale'].unique())
    prepared_products = []
    prepared_skus = []
    new_products = []
    new_skus = []

    for sku in sku_list:
        sku_data = data[data['Product variant SKU at time of sale'] == sku].reset_index(drop=True)
        daily_data = aggregate_sku_sales(sku_data)
        if len(daily_data) >= MIN_HISTORY_DAYS:
            prepared_products.append(daily_data)
            prepared_skus.append(sku)
        else:
            new_products.append(daily_data)
            new_skus.append(sku)

    return prepared_products, prepared_skus, new_products, new_skus


def calculate_stocks(predictions, dates, sku_list, inventory_filename):
    '''Собирает прогнозные остатки на горизонте прогноза для каждого SKU.'''
    stocks = pd.concat(
        [-prediction['Predicted Sold Total'] for prediction in predictions],
        axis=1,
    ).transpose().reset_index(drop=True)
    stocks.columns = dates[1:]
    inventory_data = pd.read_csv(inventory_filename)
    sku_order = [list(inventory_data['SKU']).index(sku) if sku in list(inventory_data['SKU']) else None for sku in sku_list]

    if None in sku_order:
        raise ValueError(f'Some SKU not in inventory file {inventory_filename} (unknown SKU): {sku_list[sku_order.index(None)]!r}')
    stocks[dates[0]] = list(inventory_data.loc[sku_order, dates[0]])
    stocks['SKU'] = sku_list

    for i in range(1, len(dates)):
        stocks[dates[i]] += stocks[dates[0]]
    return stocks


def normalize_dates(dates_list):
    normalized_dates = []
    for date in dates_list:
        if type(date) == str and date[2] == '/' and date[5] == '/':
            normalized_dates.append(date)
        else:
            normalized_dates.append(str(date)[5:10].replace('-', '/') + '/' + str(date)[:4])
    return normalized_dates


def _match_po_day_to_dates(po_day, dates):
    '''Сопоставляет дату PO с элементом `dates` по календарному дню.'''
    ts = pd.Timestamp(po_day).normalize()
    for d in dates:
        if pd.Timestamp(d).normalize() == ts:
            return d
    return None


def include_purchase_orders(stocks_df, po_filename, dates, sku_list):
    '''Добавляет поставки PO к остаткам, начиная с даты поступления.'''
    stocks_df_copy = stocks_df.copy()
    purchase_orders = pd.read_csv(po_filename)
    purchase_orders['Day'] = normalize_dates(purchase_orders['Day'])
    for i in range(len(purchase_orders)):
        po_day = purchase_orders['Day'].iloc[i]
        po_sku = purchase_orders['SKU'].iloc[i]
        po_qty = purchase_orders['Qty'].iloc[i]
        if po_sku not in sku_list:
            raise ValueError(f'PO references SKU not in forecast list (unknown SKU): {po_sku!r}')
        matched = po_day if po_day in dates else _match_po_day_to_dates(po_day, dates)
        if matched is not None:
            sku_index = sku_list.index(po_sku)
            matched_index = dates.index(matched)
            sku_qty_at_po_arrival = stocks_df_copy.loc[sku_index, dates[matched_index]]
            if sku_qty_at_po_arrival < 0:
                for j in range(matched_index, len(dates)):
                    stocks_df_copy.loc[sku_index, dates[j]] += po_qty - sku_qty_at_po_arrival
            else:
                for j in range(matched_index, len(dates)):
                    stocks_df_copy.loc[sku_index, dates[j]] += po_qty
    for date in dates:
        stocks_df_copy.loc[stocks_df_copy[date] < 0, date] = 0
    return stocks_df_copy


def calculate_average_sales_for_new_products(products, prediction_dates):
    early_sales_average_list = []
    for product in products:
        early_sales = list(product.iloc[:MIN_HISTORY_DAYS]['Sold'])
        early_sales_average = sum(early_sales) / MIN_HISTORY_DAYS
        early_sales_average_list.append(early_sales_average)

    average_sales_for_new_products = sum(early_sales_average_list) / len(products)
    average_new_product_prediction = pd.DataFrame()
    average_new_product_prediction['Day'] = prediction_dates
    average_new_product_prediction['Predicted Sold'] = average_sales_for_new_products

    average_new_product_prediction['Predicted Sold Total'] = average_new_product_prediction['Predicted Sold'].cumsum()
    return average_new_product_prediction


def extend_daily_sales_to_anchor(daily_df, anchor): 
    '''Добавляет нулевые продажи до общей опорной даты `anchor` (единый календарь для всех SKU).''' 
    df = daily_df.copy() 
    anchor = pd.Timestamp(anchor) 
    last = pd.Timestamp(df['Day'].max()) 
    if last >= anchor: 
        df['Date_ordinal'] = df['Day'].map(pd.Timestamp.toordinal) 
        return df 
    extra = pd.date_range(last + timedelta(days=1), anchor, freq='D') 
    extra_df = pd.DataFrame({'Day': extra, 'Sold': 0.0}) 
    base = df.drop(columns=['Date_ordinal'], errors='ignore') 
    out = pd.concat([base, extra_df], ignore_index=True) 
    out['Date_ordinal'] = out['Day'].map(pd.Timestamp.toordinal) 
    return out


def get_available_warehouse_space(stocks_df, dates, warehouse_capacity, pallets_filename):
    '''Рассчитывает свободное место склада по дням.'''
    warehouse_available = pd.DataFrame()
    warehouse_available['Day'] = dates

    pallet_data = pd.read_csv(pallets_filename)
    units_per_pallet = []
    for sku in stocks_df['SKU']:
        units_per_pallet.append(pallet_data.loc[pallet_data['SKU'] == sku, 'Units per pallet'])
    pallets_available = []
    for date in dates:
        daily_pallets = [math.ceil(float((stocks_df[date][i] / units_per_pallet[i]).iloc[0])) for i in range(len(stocks_df))]
        pallets_available.append(
            round(warehouse_capacity - sum(daily_pallets), 2)
        )
    warehouse_available['Pallets'] = pallets_available
    return warehouse_available


def build_dates(start_day, forecast_days_amount):
    '''Формирует список дат в формате, ожидаемом входными CSV-таблицами.'''
    date_range = pd.date_range(start=str(start_day)[:10], periods = forecast_days_amount + 1).astype(str)
    return [day[5:7] + '/' + day[8:10] + '/' + day[:4] for day in date_range]


def fill_in_file_templates(in_file_date):
    global INPUT_INVENTORY_LEVEL_FILENAME
    INPUT_INVENTORY_LEVEL_FILENAME = INPUT_INVENTORY_LEVEL_FILENAME.format(in_file_date)
    global INPUT_SALES_FILENAME
    INPUT_SALES_FILENAME = INPUT_SALES_FILENAME.format(in_file_date)
    global INPUT_SUPPLIED_PRODUCTS_FILENAME
    INPUT_SUPPLIED_PRODUCTS_FILENAME = INPUT_SUPPLIED_PRODUCTS_FILENAME.format(in_file_date)


def check_in_files_presence(in_file_date):
    '''Проверка, существует ли путь и является ли он файлом.'''
    fill_in_file_templates(in_file_date)

    file_path = Path(INPUT_INVENTORY_LEVEL_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_INVENTORY_LEVEL_FILENAME}')
    
    file_path = Path(INPUT_PALLETS_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_PALLETS_FILENAME}')
    
    file_path = Path(INPUT_SALES_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_SALES_FILENAME}')
    
    file_path = Path(INPUT_SUPPLIED_PRODUCTS_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_SUPPLIED_PRODUCTS_FILENAME}')


def run_pipeline(warehouse_capacity, in_file_date, forecast_days_amount):
    '''Запускает полный расчет доступной емкости склада.'''
    check_in_files_presence(in_file_date)
    print('Calculation started. Please, wait...')

    products, sku_list, new_products, new_products_sku_list = prepare_products(INPUT_SALES_FILENAME)
    predictions = []

    for product_df in products:
        product_df = extend_daily_sales_to_anchor(product_df, in_file_date)
        prediction = predict_sales(forecast_days_amount, product_df)
        prediction['Predicted Sold Total'] = prediction['Predicted Sold'].cumsum()
        predictions.append(prediction)

    dates = build_dates(products[0]['Day'].max(), forecast_days_amount)
    average_new_product_prediction = calculate_average_sales_for_new_products(products, dates[1:])

    for _ in new_products:
        predictions.append(average_new_product_prediction)

    stocks = calculate_stocks(predictions, dates, sku_list + new_products_sku_list, INPUT_INVENTORY_LEVEL_FILENAME)
    stocks = include_purchase_orders(stocks, INPUT_SUPPLIED_PRODUCTS_FILENAME, dates, sku_list)

    available_space = get_available_warehouse_space(stocks, dates, warehouse_capacity, INPUT_PALLETS_FILENAME)
    available_space.loc[available_space['Pallets'] > warehouse_capacity, 'Pallets'] = warehouse_capacity
    return available_space, stocks


def main():
    '''Точка входа: читает аргументы, выполняет расчет и сохраняет результат.'''
    # Ожидаемые параметры CLI:
    # 1) warehouse_capacity (int) — общая вместимость склада.
    # 2) date (str, формат YYYY-DD-MM) — дата, из которой формируются имена входных файлов.
    # 3) forecast_days_amount (int) — горизонт прогноза в днях.
    warehouse_capacity, in_file_date, forecast_days_amount = parse_args()
    available_space, _ = run_pipeline(warehouse_capacity, in_file_date, forecast_days_amount)
    print(available_space)
    Path('out').mkdir(parents=True, exist_ok=True)
    available_space.to_csv(OUTPUT_FILENAME, index=False)


if __name__ == '__main__':
    main()
