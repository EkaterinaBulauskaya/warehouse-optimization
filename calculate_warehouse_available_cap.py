import sys
from datetime import timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression


MIN_HISTORY_DAYS = 90  # Минимум дней истории продаж для участия SKU в прогнозе.
FORECAST_DAYS = 1096  # Горизонт прогноза в днях (примерно 3 года).
OUTPUT_FILENAME = 'warehouse_availiable_space.csv'  # Имя CSV-файла с результатом расчета.


def parse_args():
    '''Читает аргументы CLI и нормализует дату для имен входных файлов.'''
    if len(sys.argv) != 3:
        raise ValueError('Usage: python calculate_warehouse_available_cap.py <warehouse_capacity> <date>')
    warehouse_capacity = int(sys.argv[1])
    raw_date = sys.argv[2]
    normalized_date = raw_date[:4] + '-' + raw_date[8:10] + '-' + raw_date[5:7]
    return warehouse_capacity, normalized_date


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

    for sku in sku_list:
        sku_data = data[data['Product variant SKU at time of sale'] == sku].reset_index(drop=True)
        daily_data = aggregate_sku_sales(sku_data)
        if len(daily_data) >= MIN_HISTORY_DAYS:
            prepared_products.append(daily_data)
            prepared_skus.append(sku)

    return prepared_products, prepared_skus


def calculate_stocks(predictions, dates, sku_list, inventory_filename):
    '''Собирает прогнозные остатки на горизонте прогноза для каждого SKU.'''
    stocks = pd.concat(
        [-prediction['Predicted Sold Total'] for prediction in predictions],
        axis=1,
    ).transpose().reset_index(drop=True)
    stocks.columns = dates[1:]
    stocks[dates[0]] = pd.read_csv(inventory_filename)[dates[0]]
    stocks['SKU'] = sku_list

    for i in range(1, len(dates)):
        stocks[dates[i]] += stocks[dates[0]]
    return stocks


def include_purchase_orders(stocks_df, po_filename, dates, sku_list):
    '''Добавляет поставки PO к остаткам, начиная с даты поступления.'''
    purchase_orders = pd.read_csv(po_filename)
    for i in range(len(purchase_orders)):
        po_day = purchase_orders['Day'].iloc[i]
        po_sku = purchase_orders['SKU'].iloc[i]
        po_qty = purchase_orders['Qty'].iloc[i]
        for j in range(dates.index(po_day), len(dates)):
            stocks_df.loc[sku_list.index(po_sku), dates[j]] += po_qty
    return stocks_df


def get_available_warehouse_space(stocks_df, dates, warehouse_capacity):
    '''Рассчитывает свободное место склада по дням.'''
    warehouse_available = pd.DataFrame()
    warehouse_available['Day'] = dates
    warehouse_available['Space'] = [
        int(warehouse_capacity - stocks_df[dates[i]].sum()) for i in range(len(dates))
    ]
    return warehouse_available


def build_dates(start_day):
    '''Формирует список дат в формате, ожидаемом входными CSV-таблицами.'''
    date_range = pd.date_range(start=str(start_day)[:10], periods=FORECAST_DAYS + 1).astype(str)
    return [day[:4] + '/' + day[8:10] + '/' + day[5:7] for day in date_range]


def run_pipeline(warehouse_capacity, date):
    '''Запускает полный расчет доступной емкости склада.'''
    products, sku_list = prepare_products('sales_by_' + date + '.csv')
    predictions = []

    for product_df in products:
        prediction = predict_sales(FORECAST_DAYS, product_df)
        prediction['Predicted Sold Total'] = prediction['Predicted Sold'].cumsum()
        predictions.append(prediction)

    dates = build_dates(products[0]['Day'].max())

    stocks = calculate_stocks(predictions, dates, sku_list, 'inventory_level_on_' + date + '.csv')
    stocks = include_purchase_orders(stocks, 'supplied_products_by_' + date + '.csv', dates, sku_list)

    available_space = get_available_warehouse_space(stocks, dates, warehouse_capacity)
    available_space.loc[available_space['Space'] > warehouse_capacity, 'Space'] = warehouse_capacity
    return available_space


def main():
    '''Точка входа: читает аргументы, выполняет расчет и сохраняет результат.'''
    # Ожидаемые параметры CLI:
    # 1) warehouse_capacity (int) — общая вместимость склада.
    # 2) date (str, формат YYYY-DD-MM) — дата, из которой формируются имена входных файлов.
    warehouse_capacity, date = parse_args()
    available_space = run_pipeline(warehouse_capacity, date)
    print(available_space)
    available_space.to_csv(OUTPUT_FILENAME, index=False)


if __name__ == '__main__':
    main()
