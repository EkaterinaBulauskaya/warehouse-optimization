import pandas as pd
from datetime import timedelta
from sklearn.linear_model import LinearRegression
import time
from pathlib import Path

import calculate_warehouse_available_cap as cap
import get_product_abc_xyz_analysis as analysis

INPUT_PALLETS_FILENAME = 'in/in_products_for_pallet.csv'
INPUT_MOQ_FILENAME = 'in/in_products_MOQ.csv'
INPUT_FRESHNESS_WINDOW_FILENAME = 'in/in_freshness_window_data.csv'
INPUT_SALES_FILENAME_TEMPLATE = 'in/in_sales_by_{}.csv'
MIN_HISTORY_DAYS = 90  # Минимум дней истории продаж для участия SKU в прогнозе.
OUTPUT_FILENAME = 'out/out_order_recommendations.csv'  # Имя CSV-файла с результатом расчета.


def fill_filename_templates(date):
    '''Заполняет шаблоны имен файлов.'''
    global INPUT_SALES_FILENAME_TEMPLATE
    INPUT_SALES_FILENAME_TEMPLATE = INPUT_SALES_FILENAME_TEMPLATE.format(date)


def prepare_data():
    '''Читает аргументы, запускает подпроекты, заполняет шаблоны.'''
    warehouse_capacity, date, forecast_days_amount = cap.parse_args()
    available_space, stocks = cap.run_pipeline(warehouse_capacity, date, forecast_days_amount)
    abc_xyz_analysis_result = analysis.run_pipeline()
    fill_filename_templates(date)
    return available_space, stocks, abc_xyz_analysis_result


def get_detes_list(stocks):
    '''Дает список всех дат в таблице stocks.'''
    dates_list = list(stocks.keys())
    dates_list.remove('SKU')
    dates_list = pd.to_datetime(dates_list).sort_values()
    dates_list = cap.normalize_dates(list(dates_list.astype(str)))
    return dates_list


def get_products_stockout_date(stocks, recommendations):
    '''Рассчитывает дату, когда продукт закончится на складе.'''
    dates_list = get_detes_list(stocks)
    stockout = []
    for sku in recommendations['SKU']:
        product_stockout = None
        for date in dates_list:
            if float(stocks.loc[stocks['SKU'] == sku, date].iloc[0]) == 0:
                product_stockout = date
                break
        stockout.append(product_stockout)
    return stockout


def get_valid_category_products(products_df):
    '''Оставляет только категории продуктов, подходящие для дальнейшего анализа.'''
    valid_categories = ['AX', 'AY', 'BX', 'AZ', 'BY', 'CX', 'BZ', 'CY', 'CZ']
    products_df_copy = products_df.copy()
    products_df_copy['Valid_categories'] = [category in valid_categories for category in list(products_df['Category'])]
    valid_products_df = products_df.loc[products_df_copy['Valid_categories']]
    return valid_products_df, valid_categories


def fill_missing_dates(df):
    '''Заполняет пропущенные дни в диапазоне дат нулевыми продажами.'''
    df['Day'] = pd.to_datetime(df['Day'], errors='coerce')
    full_range = pd.date_range(start=df['Day'].min(), end=df['Day'].max(), freq='D')
    df = df.set_index('Day').reindex(full_range, fill_value=0)
    return df.rename_axis('Day').reset_index()


def aggregate_sku_sales(sku_df):
    '''Агрегирует продажи SKU по дням и добавляет порядковый номер даты.'''
    sku_df = sku_df.sort_values(['Day'], ascending=False)
    daily_sales = sku_df.groupby('Day', as_index=False)['Sold'].sum()
    daily_sales = fill_missing_dates(daily_sales)
    daily_sales['Date_ordinal'] = daily_sales['Day'].map(pd.Timestamp.toordinal)
    return daily_sales


def prepare_sales_data(sales_filename, sku_list):
    '''Готовит датасеты по SKU и оставляет только SKU с достаточной историей.'''
    data = pd.read_csv(sales_filename)
    data['Day'] = pd.to_datetime(data['Day'])
    data.rename(columns={'Product variant SKU at time of sale': 'SKU', 'Net items sold': 'Sold'}, inplace=True)

    prepared_products = []
    for sku in sku_list:
        sku_data = data[data['SKU'] == sku].reset_index(drop=True)
        daily_data = aggregate_sku_sales(sku_data)
        prepared_products.append(daily_data)
    return prepared_products


def predict_sales(days_ahead, last_date, sales_df, source_col='Sold', result_col='Predicted Sold'):
    '''Строит линейный прогноз продаж на заданное количество дней вперед.'''
    model = LinearRegression()
    model.fit(sales_df[['Date_ordinal']], sales_df[source_col])

    future_dates = [pd.to_datetime(last_date) + timedelta(days=i) for i in range(1, days_ahead + 1)]
    future_ordinals = [day.toordinal() for day in future_dates]

    predicted_values = model.predict(pd.DataFrame({'Date_ordinal': future_ordinals}))
    predicted_values = [float(x) if float(x) >= 0 else 0 for x in predicted_values]
    return pd.DataFrame({'Day': future_dates, result_col: predicted_values})


def predict_number_of_unit_sold(recommendations):
    '''Расчитывает общее количество товара, что может быть продано до истечения срока годности'''
    predicted_units_sold = []
    products_sales_data = prepare_sales_data(INPUT_SALES_FILENAME_TEMPLATE, list(recommendations['SKU']))
    for i in range(len(recommendations)):
        product_predicted_units_sold = None
        if recommendations.loc[i, 'Stockout'] is not None:
            stockout = recommendations.loc[i, 'Stockout']
            freshness_window = recommendations.loc[i, 'Freshness_window']
            predicted_sales = predict_sales(freshness_window, stockout, products_sales_data[i])
            product_predicted_units_sold = predicted_sales['Predicted Sold'].sum()
        predicted_units_sold.append(product_predicted_units_sold)
    return predicted_units_sold


def get_recommendations(recommendations, categories, available_space):
    '''Создает и заполняет колонки рекомендаций'''
    MOQ = pd.read_csv(INPUT_MOQ_FILENAME)
    MOQ_data = []
    for sku in recommendations['SKU']:
        MOQ_data.append(list(MOQ.loc[MOQ['SKU'] == sku, 'MOQ'])[0])
    recommendations['MOQ'] = MOQ_data
    pallet_data = pd.read_csv(INPUT_PALLETS_FILENAME)
    units_per_pallets = []
    for sku in recommendations['SKU']:
        units_per_pallets.append(list(pallet_data.loc[pallet_data['SKU'] == sku, 'Units per pallet'])[0])
    recommendations['MOQ_pallets'] = (recommendations['MOQ'] / units_per_pallets + 0.999).astype(int)
    recommendations['Units_per_pallet'] = units_per_pallets
    freshness_window_data = pd.read_csv(INPUT_FRESHNESS_WINDOW_FILENAME)
    freshness_window_data_sorted = []
    for sku in recommendations['SKU']:
        freshness_window_data_sorted.append(list(freshness_window_data.loc[freshness_window_data['SKU'] == sku, 'Freshness_window'])[0])
    recommendations['Freshness_window'] = freshness_window_data_sorted
    recommendations['Predicted_units_sold'] = predict_number_of_unit_sold(recommendations)
    recommendations['Predicted_pallets_sold'] = round(recommendations['Predicted_units_sold'] / units_per_pallets, 2)
    recommendations['Final_pallets'] = -1.0
    recommendations['Final_units'] = -1.0
    recommendations['Fullfillment_date'] = recommendations['Stockout'].copy()
    recommendations['Status'] = '---'
    for category in categories:
        recommendations, available_space = get_category_recommendations(recommendations, category, available_space)
    return recommendations


def get_category_recommendations(recommendations, category, available_space):
    category_products = recommendations.loc[recommendations['Category'] == category].copy().reset_index(drop = True)
    category_products = category_products.sort_values(by = 'Stockout')

    '''Заполняет некоторые колонки рекомендаций определенной категории продуктов'''
    available_space['Day'] = available_space['Day'].astype(str)
    # print('***', len(category_products))
    for i in range(len(category_products)):
        stockout = category_products.loc[i, 'Stockout']
        if stockout is not None:
            
            pallets_available = list(available_space.loc[available_space['Day'] == stockout, 'Pallets'])[0]
            MOQ_pallets = category_products.loc[i, 'MOQ_pallets']
            predicted_pallets_sold = category_products.loc[i, 'Predicted_pallets_sold']

            if pallets_available >= MOQ_pallets:
                if pallets_available >= predicted_pallets_sold:
                    category_products.loc[i, 'Final_pallets'] = predicted_pallets_sold
                else:
                    category_products.loc[i, 'Final_pallets'] = pallets_available
                category_products.loc[i, 'Status'] = 'Normal'

            else:
                processed_category_products = category_products.iloc[:i].copy()
                pallets_available_stockpile = processed_category_products['MOQ_pallets'] - processed_category_products['Final_pallets']
                processed_category_products['Pallets_available_stockpile'] = pallets_available_stockpile
                processed_category_products = processed_category_products.sort_values(
                        by = 'Pallets_available_stockpile', ascending = False)
                processed_category_products = processed_category_products.reset_index(drop = True)
                pallets_total_available_stockpile = pallets_available_stockpile.sum()
                
                if pallets_available + pallets_total_available_stockpile >= MOQ_pallets:
                    category_products.loc[i, 'Final_pallets'] = pallets_available
                    j = 0
                    while category_products.loc[i, 'Final_pallets'] < MOQ_pallets:
                        if processed_category_products.loc[j % i, 'Pallets_available_stockpile'] > 0:
                            processed_category_products.loc[j % i, 'Pallets_available_stockpile'] -= 1
                            category_products.loc[i, 'Final_pallets'] += 1
                        j += 1
                    category_products.loc[i, 'Status'] = 'Reallocated'
                else:
                    required_pallets_available = MOQ_pallets - pallets_total_available_stockpile
                    if pallets_available < 0:
                        required_pallets_available -= pallets_available
                    stockout_index = list(available_space.loc[available_space['Day'] == stockout].index)[0]
                    available_space_after_stockout = available_space.iloc[stockout_index + 1:]
                    suitable_available_space = available_space_after_stockout.loc[available_space_after_stockout['Pallets'] >= required_pallets_available].copy()
                    if len(suitable_available_space) > 0:
                        suitable_index = sorted(list(suitable_available_space.index))[0]
                        fullfillment_date = suitable_available_space.loc[suitable_index, 'Day']

                        suitable_pallets_available_stockpile = suitable_available_space.loc[suitable_index, 'Pallets']
                        category_products.loc[i, 'Final_pallets'] = pallets_available + suitable_pallets_available_stockpile

                        j = 0
                        while category_products.loc[i, 'Final_pallets'] < MOQ_pallets:
                            if processed_category_products.loc[j % i, 'Pallets_available_stockpile'] > 0:
                                processed_category_products.loc[j % i, 'Pallets_available_stockpile'] -= 1
                                category_products.loc[i, 'Final_pallets'] += 1
                            j += 1
                        category_products.loc[i, 'Fullfillment_date'] = fullfillment_date
                        category_products.loc[i, 'Status'] = 'PostponedCapacity'
                    else:
                        category_products.loc[i, 'Final_pallets'] = 0
                        category_products.loc[i, 'Fullfillment_date'] = None
                        category_products.loc[i, 'Status'] = 'BlockedByWarehouse'
            
            final_pallets = category_products.loc[i, 'Final_pallets']
            units_per_pallet = category_products.loc[i, 'Units_per_pallet']
            category_products.loc[i, 'Final_units'] = final_pallets * units_per_pallet

            stockout_index = list(available_space.loc[available_space['Day'] == stockout].index)[0]
            available_space.loc[stockout_index:, 'Pallets'] -= category_products.loc[i, 'Final_pallets']

        else:
            category_products.loc[i, 'Final_pallets'] = 0
            category_products.loc[i, 'Final_units'] = 0
            category_products.loc[i, 'Status'] = 'StockoutNotFound'

    drop_indexes = list(recommendations[recommendations['Category'] == category].index)
    recommendations_dropped = recommendations.drop(drop_indexes)
    recommendations = pd.concat([recommendations_dropped, category_products], ignore_index=True)
    return recommendations, available_space


def run_pipeline():
    '''Запускает расчет рекомендаций по заказу продуктов.'''
    t0 = time.time()
    print('Calculation started. Please, wait...')
    available_space, stocks, abc_xyz_analysis_result = prepare_data()
    recommendations = abc_xyz_analysis_result.loc[:, ['SKU', 'Category']]
    recommendations, categories = get_valid_category_products(recommendations)
    recommendations['Stockout'] = get_products_stockout_date(stocks, recommendations)
    recommendations = get_recommendations(recommendations, categories, available_space)
    print('Calculation time:', time.time() - t0)
    return recommendations


def main():
    '''Точка входа: читает аргументы, выполняет расчет и сохраняет результат.'''
    recommendations = run_pipeline()
    print(recommendations)
    Path('out').mkdir(parents=True, exist_ok=True)
    recommendations.to_csv(OUTPUT_FILENAME, index=False)


if __name__ == '__main__':
    main()
