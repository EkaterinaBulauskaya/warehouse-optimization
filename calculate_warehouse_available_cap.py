import sys
import pandas as pd
from sklearn.linear_model import LinearRegression
from datetime import timedelta

if len(sys.argv) == 3:
    warehouse = int(sys.argv[1])    # total warehouse capacity
    date = sys.argv[2]              # start date

# fill missing dates
def fill_date(df):
    df['Day'] = pd.to_datetime(df['Day'], errors='coerce')  # Преобразуем в datetime
    full_range = pd.date_range(start=df['Day'].min(), end=df['Day'].max(), freq='D')
    df = df.set_index('Day')
    df = df.reindex(full_range, fill_value=0)
    return df.rename_axis('Day').reset_index()

def predict_sales(days_ahead, df1, df1_col = 'Sold', rez_col = 'Predicted Sold'):
    model = LinearRegression()
    model.fit(df1[['Date_ordinal']], df1[df1_col])
    last_date = df1['Day'].max()
    # future_dates = [last_date + timedelta(days=i) for i in range(1, days_ahead + 1)]
    future_dates = [pd.to_datetime(last_date) + timedelta(days=i) for i in range(1, days_ahead + 1)]
    future_ordinals = [d.toordinal() for d in future_dates]
    predicted_sales = model.predict(pd.DataFrame({'Date_ordinal': future_ordinals}))
    predicted_sales = [float(x) if float(x) >= 0 else 0 for x in predicted_sales]
    return pd.DataFrame({'Day': future_dates, rez_col: predicted_sales})

def prepare_prod(filename):
    data = pd.read_csv(filename)
    data['Day'] = pd.to_datetime(data['Day'])
    prod_list = list(data['Product variant SKU at time of sale'].unique())
    prod = [data[data['Product variant SKU at time of sale'] == sku].reset_index(drop = True) for sku in prod_list]

    for i in range(len(prod)):
        prod[i] = prod[i].sort_values(['Day'], ascending = False)
        term_prod = pd.DataFrame()
        term_prod['Day'] = prod[i]['Day'].unique()
        sold = []
        for date in list(prod[i]['Day'].unique()):
            sold.append(prod[i][prod[i]['Day'] == date]['Net items sold'].sum())
        term_prod['Sold'] = sold
        prod[i] = term_prod
        prod[i] = fill_date(prod[i])
        prod[i]['Date_ordinal'] = prod[i]['Day'].map(pd.Timestamp.toordinal)

    term_prod = []
    term_list = []
    for i in range(len(prod)):
        if len(prod[i]) >= 90:
            term_prod.append(prod[i])
            term_list.append(prod_list[i])
    return term_prod, term_list

def get_stocks(pred, dates, prod_list, filename):
    stocks = pd.concat([-pred[i]['Predicted Sold Total'] for i in range(len(pred))], axis = 1).transpose().reset_index(drop = True)
    stocks.columns = dates[1:]
    stocks[dates[0]] = pd.read_csv(filename)[dates[0]]
    stocks['SKU'] = prod_list
    for i in range(1, len(dates)):
        stocks[dates[i]] += stocks[dates[0]]
    return stocks

def include_PO(stocks_df, PO_filename, dates, prod_list):
    PO = pd.read_csv(PO_filename)
    for i in range(len(PO)):
        for j in range(dates.index(PO['Day'].iloc[i]), len(dates)):
            stocks_df.loc[prod_list.index(PO['SKU'].iloc[i]), dates[j]] += PO['Qty'].iloc[i]
    return stocks_df

def get_available_warehouse_space(stocks_df, dates, warehouse):
    warehouse_available = pd.DataFrame()
    warehouse_available['Day'] = dates
    warehouse_available['Space'] = [int(warehouse - stocks_df[dates[i]].sum()) for i in range(len(dates))]
    return warehouse_available

date = date[:4] + '-' + date[8:10] + '-' + date[5:7]
prod, prod_list = prepare_prod('sales_by_' + date + '.csv')
pred = []
for i in range(len(prod)):
    pred.append(predict_sales(1096, prod[i]))
    pred[i]['Predicted Sold Total'] = pred[i]['Predicted Sold'].cumsum()
dates = list(day[:4] + '/' + day[8:10] +'/' + day[5:7] for day in pd.date_range(start = str(prod[0]['Day'].max())[:10], periods = 1097).astype(str))

stocks = get_stocks(pred, dates, prod_list, 'inventory_level_on_' + date + '.csv')
stocks = include_PO(stocks, 'supplied_products_by_' + date + '.csv', dates, prod_list)
availiable_space = get_available_warehouse_space(stocks, dates, warehouse)
availiable_space['Space'][availiable_space['Space'] > warehouse] = warehouse
print(availiable_space)
availiable_space.to_csv('warehouse_availiable_space.csv')
