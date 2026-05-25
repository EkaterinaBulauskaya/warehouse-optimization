import sys
import pandas as pd
from datetime import timedelta
from sklearn.linear_model import LinearRegression
from pathlib import Path
import calculate_warehouse_available_cap as cap
import get_product_abc_xyz_analysis as analysis

INPUT_ABC_XYZ_FILENAME = 'in/in_for_abc_xyz_analysis.csv'
INPUT_PALLETS_FILENAME = 'in/in_products_for_pallet.csv'
INPUT_MOQ_FILENAME = 'in/in_products_MOQ.csv'
INPUT_FRESHNESS_WINDOW_FILENAME = 'in/in_freshness_window_data.csv'
INPUT_SUPPLIED_PRODUCTS_FILENAME = 'in/in_supplied_products.csv'
INPUT_TIER_PRICES_FILENAME = 'in/in_tier_prices.csv'
INPUT_SALES_FILENAME_TEMPLATE = 'in/in_sales_by_{}.csv'
MIN_HISTORY_DAYS = 90  # Минимум дней истории продаж для участия SKU в прогнозе.
OUTPUT_FILENAME = 'out/out_order_recommendations.csv'  # Имя CSV-файла с результатом расчета.
DAILY_STORAGE_COST_PER_PALLET = None


def fill_filename_template(date):
    '''Заполняет шаблоны имен файлов.'''
    global INPUT_SALES_FILENAME_TEMPLATE
    INPUT_SALES_FILENAME_TEMPLATE = INPUT_SALES_FILENAME_TEMPLATE.format(date)


def parse_args():
    '''Читает аргументы CLI и нормализует дату для имен входных файлов.'''
    if len(sys.argv) != 5:
        raise ValueError('Usage: python calculate_warehouse_available_cap.py <warehouse_capacity> <in_file_date> <forecast_days_amount> <daily_storage_cost_per_pallet>')
    warehouse_capacity = int(sys.argv[1])
    raw_date = sys.argv[2]
    normalized_date = raw_date[:4] + '-' + raw_date[8:10] + '-' + raw_date[5:7]
    forecast_days_amount = int(sys.argv[3])
    daily_st_cost_pp = float(sys.argv[4])
    return warehouse_capacity, normalized_date, forecast_days_amount, daily_st_cost_pp


def prepare_data():
    '''Читает аргументы, запускает подпроекты, заполняет шаблоны.'''
    warehouse_capacity, date, forecast_days_amount, daily_st_cost_pp = parse_args()
    global DAILY_STORAGE_COST_PER_PALLET
    DAILY_STORAGE_COST_PER_PALLET = daily_st_cost_pp
    available_space, stocks = cap.run_pipeline(warehouse_capacity, date, forecast_days_amount)
    available_space['Pallets'] = available_space['Pallets'].astype(float)
    abc_xyz_analysis_result = analysis.run_pipeline()
    fill_filename_template(date)
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
    products_supplies = pd.read_csv(INPUT_SUPPLIED_PRODUCTS_FILENAME)
    freshness_window = pd.read_csv(INPUT_FRESHNESS_WINDOW_FILENAME)
    first_date = dates_list[0]
    stockout = []
    for sku in recommendations['SKU']:
        product_stockout = None
        for date in dates_list:
            if float(stocks.loc[stocks['SKU'] == sku, date].iloc[0]) == 0:
                product_stockout = date
                break

        first_date_reserve = stocks.loc[stocks['SKU'] == sku, first_date]
        sku_supplies = products_supplies.loc[products_supplies['SKU'] == sku]
        sku_supplies.loc[:, 'Day'] = pd.to_datetime(sku_supplies['Day'])
        first_date_ts = pd.to_datetime(first_date)
        past_supplies = sku_supplies[sku_supplies['Day'] < first_date_ts]
        past_supplies_sorted = past_supplies.sort_values(
            by = 'Day', ascending = True).reset_index(drop = True)

        sku_freshness_window = freshness_window.loc[freshness_window['SKU'] == sku, 'Freshness_window']
        sku_freshness_window = list(sku_freshness_window)[0]
        first_date_reserve = list(first_date_reserve)[0]
        if past_supplies_sorted['Qty'].loc[0] >= first_date_reserve:
            expiring_date = past_supplies_sorted.loc[0, 'Day'] + timedelta(days = sku_freshness_window)
            expiring_date = cap.normalize_dates([str(expiring_date)])[0]
            if (product_stockout is None or expiring_date < product_stockout) and expiring_date in dates_list:
                product_stockout = expiring_date
        else:
            total_reserve = 0
            current_silling_supply_index = -1
            for i in range(len(past_supplies_sorted)):
                supply_qty = past_supplies_sorted.loc[i, 'Qty']
                if supply_qty + total_reserve >= first_date_reserve:
                    total_reserve += supply_qty
                    current_silling_supply_index = i
                else:
                    break

            write_off = 0
            for i in range(current_silling_supply_index, -1, -1):
                expiring_date = past_supplies_sorted.loc[i, 'Day'] + timedelta(days = sku_freshness_window)
                if expiring_date >= product_stockout:
                    break
                else:
                    product_reserve = stocks.loc[stocks['SKU'] == sku, expiring_date] - write_off
                    total_reserve -= past_supplies_sorted.loc[i, 'Qty']
                    if product_reserve >= total_reserve:
                        write_off += product_reserve - total_reserve
                        if total_reserve == 0:
                            product_stockout = expiring_date
                    elif product_reserve < 0:
                        for j in range(dates_list.index(expiring_date), -1, -1):
                            if stocks.loc[stocks['SKU'] == sku, dates_list[j]] >= write_off:
                                product_stockout = dates_list[j]

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
    predicted_units_sold_per_day = []
    products_sales_data = prepare_sales_data(INPUT_SALES_FILENAME_TEMPLATE, list(recommendations['SKU']))
    for i in range(len(recommendations)):
        product_predicted_units_sold = None
        if recommendations.loc[i, 'Stockout'] is not None:
            stockout = recommendations.loc[i, 'Stockout']
            freshness_window = recommendations.loc[i, 'Freshness_window']
            predicted_sales = predict_sales(freshness_window, stockout, products_sales_data[i])
            product_predicted_units_sold = predicted_sales['Predicted Sold'].sum()
            product_predicted_units_sold_per_day = predicted_sales.loc[1, 'Predicted Sold'] - predicted_sales.loc[0, 'Predicted Sold']
        predicted_units_sold.append(product_predicted_units_sold)
        predicted_units_sold_per_day.append(product_predicted_units_sold_per_day)
    return predicted_units_sold, predicted_units_sold_per_day


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
    recommendations['Predicted_units_sold'], recommendations['Predicted_units_sold_per_day'] = predict_number_of_unit_sold(recommendations)
    recommendations['Predicted_pallets_sold'] = round(recommendations['Predicted_units_sold'] / units_per_pallets, 2)
    recommendations['Final_pallets'] = -1.0
    recommendations['Final_units'] = -1.0
    recommendations['Fullfillment_date'] = recommendations['Stockout'].copy()
    recommendations['Status'] = '---'
    for category in categories:
        recommendations, available_space = get_category_recommendations(recommendations, category, available_space)
    return recommendations


def prepare_category_products(recommendations, category):
    '''Отбирает продукты заданной категории, сортирует их по дате stockout.'''
    category_products = (
        recommendations.loc[recommendations['Category'] == category]
        .copy()
        .reset_index(drop=True)
    )
    return category_products.sort_values(by='Stockout')


def allocate_normal_case(row, pallets_available):
    '''Обрабатывает случай, когда места на складе достаточно для заказа.'''
    MOQ = row['MOQ_pallets']
    predicted = row['Predicted_pallets_sold']

    if pallets_available >= predicted:
        final = predicted
    else:
        final = pallets_available

    return final, 'Normal'


def reallocate_from_stockpile(category_products, i, pallets_available):
    '''Обрабатывает случай, когда недостающее место можно "забрать" у уже обработанных продуктов.'''
    processed = category_products.iloc[:i].copy()
    processed['Pallets_available_stockpile'] = (
        processed['MOQ_pallets'] - processed['Final_pallets']
    )

    processed = processed.sort_values(
        by='Pallets_available_stockpile', ascending=False
    ).reset_index(drop=True)

    total_stockpile = processed['Pallets_available_stockpile'].sum()
    MOQ = category_products.loc[i, 'MOQ_pallets']

    if pallets_available + total_stockpile < MOQ:
        return None

    final = pallets_available
    j = 0
    while final < MOQ:
        idx = j % i
        if processed.loc[idx, 'Pallets_available_stockpile'] > 0:
            processed.loc[idx, 'Pallets_available_stockpile'] -= 1
            final += 1
        j += 1
    return final, 'Reallocated'


def postpone_or_block(category_products, i, pallets_available, available_space, stockout):
    '''Обрабатывает случай, когда дата заказа преносится из-за нехватки места.'''
    MOQ = category_products.loc[i, 'MOQ_pallets']

    processed = category_products.iloc[:i].copy()
    processed['Pallets_available_stockpile'] = (
        processed['MOQ_pallets'] - processed['Final_pallets']
    )
    total_stockpile = processed['Pallets_available_stockpile'].sum()

    required = MOQ - total_stockpile
    if pallets_available < 0:
        required -= pallets_available

    stockout_index = list(available_space.loc[available_space['Day'] == stockout].index)[0]
    future_space = available_space.iloc[stockout_index + 1:]
    suitable = future_space.loc[future_space['Pallets'] >= required]
    if len(suitable) == 0:
        return 0, None, 'BlockedByWarehouse'

    suitable_index = sorted(list(suitable.index))[0]
    fullfillment_date = suitable.loc[suitable_index, 'Day']
    extra_pallets = suitable.loc[suitable_index, 'Pallets']

    final = pallets_available + extra_pallets
    j = 0
    while final < MOQ:
        idx = j % i
        if processed.loc[idx, 'Pallets_available_stockpile'] > 0:
            processed.loc[idx, 'Pallets_available_stockpile'] -= 1
            final += 1
        j += 1

    return final, fullfillment_date, 'PostponedCapacity'


def update_available_space(available_space, stockout, used_pallets):
    '''Обновляет данные о доступном месте на складе'''
    stockout_index = list(available_space.loc[available_space['Day'] == stockout].index)[0]
    available_space.loc[stockout_index:, 'Pallets'] -= used_pallets
    return available_space


def process_single_product(category_products, i, available_space):
    '''Обрабатывает один продукт из категории'''
    stockout = category_products.loc[i, 'Stockout']

    if stockout is None:
        category_products.loc[i, 'Final_pallets'] = 0
        category_products.loc[i, 'Final_units'] = 0
        category_products.loc[i, 'Status'] = 'StockoutNotFound'
        return category_products, available_space

    pallets_available = list(available_space.loc[available_space['Day'] == stockout, 'Pallets'])[0]
    MOQ = category_products.loc[i, 'MOQ_pallets']

    if pallets_available >= MOQ:
        final, status = allocate_normal_case(category_products.loc[i], pallets_available)
        category_products.loc[i, 'Final_pallets'] = final
        category_products.loc[i, 'Status'] = status

    else:
        realloc = reallocate_from_stockpile(category_products, i, pallets_available)
        if realloc is not None:
            final, status = realloc
            category_products.loc[i, 'Final_pallets'] = final
            category_products.loc[i, 'Status'] = status
        else:
            final, date, status = postpone_or_block(
                category_products, i, pallets_available, available_space, stockout
            )
            category_products.loc[i, 'Final_pallets'] = final
            category_products.loc[i, 'Fullfillment_date'] = date
            category_products.loc[i, 'Status'] = status

    units_per_pallet = category_products.loc[i, 'Units_per_pallet']
    category_products.loc[i, 'Final_units'] = category_products.loc[i, 'Final_pallets'] * units_per_pallet
    used_pallets = (category_products.loc[i, 'Final_pallets'] + 0.999).astype(int)
    available_space = update_available_space(available_space, stockout, used_pallets)
    return category_products, available_space


def get_category_recommendations(recommendations, category, available_space):
    '''Заполняет некоторые колонки рекомендаций определенной категории продуктов'''
    category_products = prepare_category_products(recommendations, category)
    available_space['Day'] = available_space['Day'].astype(str)

    for i in range(len(category_products)):
        category_products, available_space = process_single_product(
            category_products, i, available_space
        )

    drop_indexes = list(recommendations[recommendations['Category'] == category].index)
    recommendations_dropped = recommendations.drop(drop_indexes)
    recommendations = pd.concat([recommendations_dropped, category_products], ignore_index=True)

    return recommendations, available_space


def prefill_optimal_column(recommendations):
    recommendations.loc[[fd is None for fd in list(recommendations['Fullfillment_date'])], 'Optimal_pallets'] = 0

    status_true_recommendations = recommendations[[fd is not None for fd in list(recommendations['Fullfillment_date'])]]
    const_cond = status_true_recommendations['Final_pallets'] == status_true_recommendations['MOQ_pallets']
    status_true_recommendations.loc[const_cond, 'Optimal_pallets'] = status_true_recommendations['MOQ_pallets']

    recommendations[[fd is not None for fd in list(recommendations['Fullfillment_date'])]] = status_true_recommendations
    return recommendations


def calculate_profit(pallets, moq, units_per_pallet, tier_prices, unit_cost, palletadays):
    if pallets < moq:
        return None

    units_num = units_per_pallet * pallets
    tier_prices = tier_prices.reset_index(drop = True)

    revenue_per_pallet = round(units_per_pallet * unit_cost, 2)
    vendor_cost = 0
    if len(tier_prices) == 1:
        vendor_cost = float(tier_prices['Price'].iloc[0]) * units_num
    else:
        for n in range(len(tier_prices)):
            frm = tier_prices.loc[n, 'From']
            to = tier_prices.loc[n, 'To']
            price = float(tier_prices.loc[n, 'Price'])
            if frm == '-':
                to = float(to)
                if to < units_num:
                    vendor_cost += to * price
                else:
                    vendor_cost += units_num * price
            elif to == '-':
                frm = float(frm)
                if units_num > frm:
                    vendor_cost += (units_num - frm) * price
            else:
                frm = float(frm)
                to = float(to)
                if units_num > to:
                    vendor_cost += (to - frm) * price
                elif units_num > frm:
                    vendor_cost += (units_num - frm) * price

    stock_cost = DAILY_STORAGE_COST_PER_PALLET * palletadays
    profit = round(pallets * revenue_per_pallet - vendor_cost - stock_cost,2)
    return profit


def get_number_palletaday_stored(pallets, units_per_pallet, units_sold_per_day):
    total_units = pallets * units_per_pallet
    palletadyds = 0
    days = 0
    while total_units > 0 and days < 365:
        days += 1
        palletadyds += total_units // units_per_pallet + int(total_units % units_per_pallet != 0)
        total_units -= units_sold_per_day
    return palletadyds


def get_profit_table(product_data):
    table_limit = int(product_data['Final_pallets'].max() + 0.999)
    sku_list = list(product_data['SKU'])

    profit_table = pd.DataFrame()
    MOQ = pd.read_csv(INPUT_MOQ_FILENAME)
    tier_prices = pd.read_csv(INPUT_TIER_PRICES_FILENAME)
    product_costs = pd.read_csv(INPUT_ABC_XYZ_FILENAME)
    for sku in sku_list:
        moq = list(MOQ.loc[MOQ['SKU'] == sku, 'MOQ'])[0]
        tier = tier_prices[tier_prices['SKU'] == sku].reset_index(drop = True)
        tier = tier[['SKU', 'From', 'To', 'Price']]
        cost = list(product_costs.loc[product_costs['SKU'] == sku, 'Cost'])[0]
        upp = list(product_data.loc[product_data['SKU'] == sku, 'Units_per_pallet'])[0]
        uspd = list(product_data.loc[product_data['SKU'] == sku, 'Predicted_units_sold_per_day'])[0]
        moq = int(moq / upp + 0.999)

        sku_profit = []
        for i in range(table_limit + 1):
            pallets = get_number_palletaday_stored(i, upp, uspd)
            sku_profit.append(calculate_profit(i, moq, upp , tier, cost, pallets))
        profit_table[sku] = sku_profit
    return profit_table


def get_recommendations_optimal(recommendations):
    recommendations['Optimal_pallets'] = None
    recommendations = prefill_optimal_column(recommendations)

    to_be_optimized_recommendations = recommendations.loc[[op == None for op in list(recommendations['Optimal_pallets'])]]
    sku_list = list(to_be_optimized_recommendations['SKU'])
    profit_table = get_profit_table(to_be_optimized_recommendations)

    for sku in sku_list:
        final_pallets_rez = list(recommendations.loc[recommendations['SKU'] == sku, 'Final_pallets'])[0]
        sku_cond = to_be_optimized_recommendations['SKU'] == sku
        to_be_optimized_recommendations.loc[sku_cond, 'Optimal_pallets'] = profit_table.loc[:final_pallets_rez, sku].idxmax()

    recommendations.loc[[op == None for op in list(recommendations['Optimal_pallets'])]] = to_be_optimized_recommendations
    return recommendations


def check_in_files_presence(in_file_date):
    '''Проверка, существует ли путь и является ли он файлом.'''
    fill_filename_template(in_file_date)

    file_path = Path(INPUT_PALLETS_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_PALLETS_FILENAME}')

    file_path = Path(INPUT_MOQ_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_MOQ_FILENAME}')

    file_path = Path(INPUT_FRESHNESS_WINDOW_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_FRESHNESS_WINDOW_FILENAME}')

    file_path = Path(INPUT_SALES_FILENAME_TEMPLATE)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_SALES_FILENAME_TEMPLATE}')

    file_path = Path(INPUT_SUPPLIED_PRODUCTS_FILENAME)
    if not file_path.is_file():
        raise ValueError(f'No such file in directory: {INPUT_SUPPLIED_PRODUCTS_FILENAME}')


def run_pipeline():
    '''Запускает расчет рекомендаций по заказу продуктов.'''
    print('Calculation started. Please, wait...')
    available_space, stocks, abc_xyz_analysis_result = prepare_data()
    recommendations = abc_xyz_analysis_result.loc[:, ['SKU', 'Category']]
    recommendations, categories = get_valid_category_products(recommendations)
    recommendations['Stockout'] = get_products_stockout_date(stocks, recommendations)
    recommendations = get_recommendations(recommendations, categories, available_space)
    recommendations = get_recommendations_optimal(recommendations)
    return recommendations


def main():
    '''Точка входа: читает аргументы, выполняет расчет и сохраняет результат.'''
    recommendations = run_pipeline()
    print(recommendations)
    Path('out').mkdir(parents=True, exist_ok=True)
    recommendations.to_csv(OUTPUT_FILENAME, index=False)


if __name__ == '__main__':
    main()
