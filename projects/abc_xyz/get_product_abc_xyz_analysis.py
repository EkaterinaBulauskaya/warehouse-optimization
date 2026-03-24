import pandas as pd
from sklearn.linear_model import LinearRegression


INPUT_FILENAME = 'in_for_abc_xyz_analysis.csv'  # Имя CSV-файла с данными для расчета
MIN_HISTORY_DAYS = 90  # Минимум дней истории продаж для участия SKU в прогнозе
OUTPUT_FILENAME = 'out_abc_xyz_analysis_results.csv' # Имя CSV-файла с результатами расчета


def repair_product(product, sells_col = 'Sold'):
    '''Заполняет нулевые продажи продукта, если его не было на складе'''
    new_product = product.copy()
    model = LinearRegression()
    model.fit(product[product['Status'] == 1][['Date_ordinal']], product[product][sells_col])
    repair_ordinals  = product[product['Status'] == 0]['Date_ordinal']
    predicted_sales = model.predict(pd.DataFrame({'Date_ordinal': repair_ordinals }))
    new_product['Sold'] = new_product['Sold'].astype('float32')
    new_product.loc[new_product['Status'] == 0, 'Sold'] = [round(float(x), 2) if float(x) >= 0 else 0 for x in predicted_sales]
    return new_product


def prepare_products(filename):
    '''Готовит датасеты по SKU и оставляет только SKU с достаточной историей'''
    data = pd.read_csv(filename)
    # Удаляем служебные колонки индекса, если CSV был сохранен с index=True
    data = data.loc[:, ~data.columns.str.startswith('Unnamed')]
    data['Day'] = pd.to_datetime(data['Day'])

    sku_list = list(data['SKU'].unique())
    prepared_products = []
    prepared_skus = []

    for sku in sku_list:
        sku_data = data[data['SKU'] == sku].reset_index(drop=True)
        if len(sku_data) >= MIN_HISTORY_DAYS:
            sku_data['Date_ordinal'] = sku_data['Day'].map(pd.Timestamp.toordinal)
            prepared_products.append(sku_data)
            prepared_skus.append(sku)

            if len(sku_data[sku_data['Status'] == 0]) > 0:
                prepared_products[-1] = repair_product(sku_data)

    return prepared_products, prepared_skus


def get_abc_analysis(products):
    '''Проводит ABC-анализ продуктов (по маржинальности)'''
    total_margin = 0
    for i in range(len(products)):
        margin = round(((products[i]['Price'] - products[i]['Cost']) * products[i]['Sold']).sum(), 2)
        total_margin += margin

    margin_table = pd.DataFrame()
    margin_table['SKU'] = [products[i].loc[0, 'SKU'] for i in range(len(products))]
    margin_table['Margin'] = [round(((products[i]['Price'] - products[i]['Cost']) * products[i]['Sold']).sum(), 2) for i in range(len(products))]
    margin_table['Share'] = round(margin_table['Margin'] / total_margin * 100, 2)
    margin_table = margin_table.sort_values(by = 'Share', ascending = False).reset_index(drop = True)
    margin_table['Margin_cum'] = margin_table['Margin'].cumsum()
    margin_table['Category'] = '-'
    margin_table.loc[margin_table['Margin_cum'] < total_margin * 0.95, 'Category'] = 'B'
    margin_table.loc[margin_table['Margin_cum'] < total_margin * 0.8, 'Category'] = 'A'
    margin_table.loc[margin_table['Share'] < 3, 'Category'] = 'B'
    margin_table.loc[margin_table['Margin_cum'] >= total_margin * 0.95, 'Category'] = 'C'
    margin_table.loc[margin_table['Share'] <= 0, 'Category'] = 'D'
    return margin_table


def get_xyz_analysis(products):
    '''Проводит XYZ-анализ продуктов (по стабильности спроса)'''
    for i in range(len(products)):
        products[i]['Day'] = [day[:7] for day in products[i]['Day'].astype('str')]

    products_months = []
    for i in range(len(products)):
        product = pd.DataFrame()
        product['Month'] = products[i]['Day'].unique()
        product['SKU'] = products[i].loc[0, 'SKU']
        product['Sold'] = [products[i].loc[products[i]['Day'] == month, 'Sold'].sum() for month in product['Month']]
        products_months.append(product)

    stability_table = pd.DataFrame()
    stability_table['SKU'] = [products_months[i].loc[0, 'SKU'] for i in range(len(products_months))]
    stability_table['Avg_sold'] = [round(products_months[i]['Sold'].sum() / len(products_months[i]), 2) for i in range(len(products_months))]
    stability_table['St_deviation'] = [(((products_months[i]['Sold'] - stability_table.loc[i, 'Avg_sold'])**2).sum() / len(products_months[i]))**(1/2) for i in range(len(products_months))]
    stability_table['Coeff_variation'] = stability_table['St_deviation'] / stability_table['Avg_sold'] * 100
    stability_table['Category'] = 'W'
    stability_table.loc[stability_table['Coeff_variation'] > 0, 'Category'] = 'X'
    stability_table.loc[stability_table['Coeff_variation'] > 25, 'Category'] = 'Y'
    stability_table.loc[stability_table['Coeff_variation'] > 50, 'Category'] = 'Z'
    stability_table.loc[stability_table['Coeff_variation'] > 100, 'Category'] = 'W'
    return stability_table


def merge_analysis_result(margin_table, stability_table, sku_list):
    '''Объединяет результаты ABC- и XYZ-анализа в одну таблицу'''
    result_matrix = pd.DataFrame()
    result_matrix['SKU'] = sku_list
    result_matrix['Margin'] = [list(margin_table[margin_table['SKU'] == sku]['Margin'])[0] for sku in sku_list]
    result_matrix['Variation'] = [round(list(stability_table[stability_table['SKU'] == sku]['Coeff_variation'])[0], 2) for sku in sku_list]
    result_matrix['Category'] = [list(margin_table[margin_table['SKU'] == sku]['Category'])[0] + list(stability_table[stability_table['SKU'] == sku]['Category'])[0] for sku in sku_list]
    return result_matrix.sort_values(by = 'Category').reset_index(drop = True)


def run_pipeline():
    '''Запускает расчет категорий продуктов'''
    print('Calculation started...')
    products, sku_list = prepare_products(INPUT_FILENAME)
    
    margin_table = get_abc_analysis(products)
    stability_table = get_xyz_analysis(products)

    result_matrix = merge_analysis_result(margin_table, stability_table, sku_list)
    return result_matrix


def main():
    '''Точка входа: выполняет расчет и сохраняет результат'''
    abc_xyz_matrix = run_pipeline()
    print(abc_xyz_matrix)
    abc_xyz_matrix.to_csv(OUTPUT_FILENAME, index=False)


if __name__ == '__main__':
    main()
