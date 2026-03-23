"""Тесты для calculate_warehouse_available_cap.

Карта классов к `CALCULATION_ISSUES.md`: `TestPriority3Issues` — общий календарь, PO по датам, остатки по SKU;
`TestPriority2Issues` — неизвестный SKU в PO. Функции уровня модуля (`test_parse_args_*`, `test_build_dates`, …) —
смоук и вспомогательная логика без отдельной записи в issues.

TDD: класс `TestPriority3Issues` задаёт **ожидаемое корректное** поведение —
общий календарь по anchor-дате, сопоставление дат поставок с `dates`, начальные остатки по `SKU`.
"""

import pandas as pd
import pytest

import calculate_warehouse_available_cap as cap


def test_parse_args_normalizes_date(monkeypatch):
    monkeypatch.setattr(
        cap.sys,
        "argv",
        ["calculate_warehouse_available_cap.py", "100000", "2025-31-12", "30"],
    )

    warehouse_capacity, normalized_date, forecast_days_amount = cap.parse_args()

    assert warehouse_capacity == 100000
    assert normalized_date == "2025-12-31"
    assert forecast_days_amount == 30


def test_parse_args_raises_on_invalid_argv(monkeypatch):
    monkeypatch.setattr(cap.sys, "argv", ["calculate_warehouse_available_cap.py", "100000"])

    with pytest.raises(ValueError):
        cap.parse_args()


def test_build_dates_returns_expected_format_and_size():
    dates = cap.build_dates(pd.Timestamp("2025-12-31"), 3)

    assert dates == ["12/31/2025", "01/01/2026", "01/02/2026", "01/03/2026"]


def test_fill_missing_dates_fills_gap_with_zero():
    source = pd.DataFrame(
        {
            "Day": ["2025-12-01", "2025-12-03"],
            "Sold": [5, 9],
        }
    )

    result = cap.fill_missing_dates(source)

    assert len(result) == 3
    assert result["Day"].dt.strftime("%Y-%m-%d").tolist() == [
        "2025-12-01",
        "2025-12-02",
        "2025-12-03",
    ]
    assert result["Sold"].tolist() == [5, 0, 9]


def test_run_pipeline_smoke(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    date_tag = "2025-12-31"
    forecast_days = 5
    warehouse_capacity = 1000
    sku = "SKU-1"

    sales_days = pd.date_range("2025-10-02", "2025-12-31", freq="D")
    sales_df = pd.DataFrame(
        {
            "Day": sales_days.strftime("%m/%d/%Y"),
            "Product variant SKU at time of sale": [sku] * len(sales_days),
            "Net items sold": [1] * len(sales_days),
        }
    )
    sales_df.to_csv(tmp_path / f"in_sales_by_{date_tag}.csv", index=False)

    inventory_df = pd.DataFrame(
        {
            "SKU": [sku],
            "12/31/2025": [200],
        }
    )
    inventory_df.to_csv(tmp_path / f"in_inventory_level_on_{date_tag}.csv", index=False)

    po_df = pd.DataFrame(columns=["Day", "SKU", "Qty"])
    po_df.to_csv(tmp_path / f"in_supplied_products_by_{date_tag}.csv", index=False)

    result = cap.run_pipeline(warehouse_capacity, date_tag, forecast_days)

    assert list(result.columns) == ["Day", "Space"]
    assert len(result) == forecast_days + 1
    assert (result["Space"] <= warehouse_capacity).all()


def test_predict_sales_starts_day_after_last_sale():
    sales = pd.DataFrame(
        {
            "Day": pd.to_datetime(["2025-12-01", "2025-12-31"]),
            "Sold": [1.0, 2.0],
            "Date_ordinal": [pd.Timestamp(d).toordinal() for d in ["2025-12-01", "2025-12-31"]],
        }
    )
    out = cap.predict_sales(3, sales)
    assert len(out) == 3
    assert out["Day"].iloc[0] == pd.Timestamp("2026-01-01")
    assert out["Predicted Sold"].notna().all()


class TestPriority2Issues:
    """PO с SKU вне списка прогноза — явное исключение с понятным текстом."""

    def test_po_unknown_sku_raises_clear_error(self, tmp_path):
        """SKU из PO отсутствует в `sku_list` — явное `ValueError`, не падение на `list.index`."""
        dates = ["12/31/2025", "01/01/2026", "01/02/2026"]
        stocks = pd.DataFrame(
            {
                "SKU": ["S1"],
                "12/31/2025": [10.0],
                "01/01/2026": [0.0],
                "01/02/2026": [0.0],
            }
        )
        po = pd.DataFrame(
            {"Day": ["01/01/2026"], "SKU": ["UNKNOWN"], "Qty": [5]}
        )
        po_path = tmp_path / "po.csv"
        po.to_csv(po_path, index=False)

        with pytest.raises(ValueError, match="not in forecast"):
            cap.include_purchase_orders(stocks.copy(), str(po_path), dates, ["S1"])


class TestPriority3Issues:
    """Общий календарь по anchor, сопоставление дат PO с `dates`, начальные остатки по колонке `SKU`, не по порядку строк."""

    def test_multi_sku_forecast_aligns_to_shared_anchor_calendar(
        self, tmp_path, monkeypatch
    ):
        """Общая опорная дата; первый день прогноза каждого SKU совпадает с `dates[1]`."""
        monkeypatch.chdir(tmp_path)
        date_tag = "2025-12-31"
        forecast_days = 3

        early_end = pd.date_range(end="2025-12-20", periods=95, freq="D")
        late_end = pd.date_range(end="2025-12-31", periods=95, freq="D")

        rows = []
        for d in early_end:
            rows.append(
                {
                    "Day": d.strftime("%m/%d/%Y"),
                    "Product variant SKU at time of sale": "EARLY",
                    "Net items sold": 1,
                }
            )
        for d in late_end:
            rows.append(
                {
                    "Day": d.strftime("%m/%d/%Y"),
                    "Product variant SKU at time of sale": "LATE",
                    "Net items sold": 1,
                }
            )
        pd.DataFrame(rows).to_csv(tmp_path / f"in_sales_by_{date_tag}.csv", index=False)

        pd.DataFrame(
            {
                "SKU": ["EARLY", "LATE"],
                "12/31/2025": [50, 60],
            }
        ).to_csv(tmp_path / f"in_inventory_level_on_{date_tag}.csv", index=False)

        pd.DataFrame(columns=["Day", "SKU", "Qty"]).to_csv(
            tmp_path / f"in_supplied_products_by_{date_tag}.csv", index=False
        )

        products, sku_list = cap.prepare_products(tmp_path / f"in_sales_by_{date_tag}.csv")
        assert len(products) == 2
        assert sku_list[0] == "EARLY"

        anchor = max(pd.Timestamp(p["Day"].max()) for p in products)
        extended = [cap.extend_daily_sales_to_anchor(p, anchor) for p in products]

        predictions = []
        for product_df in extended:
            pred = cap.predict_sales(forecast_days, product_df)
            pred["Predicted Sold Total"] = pred["Predicted Sold"].cumsum()
            predictions.append(pred)

        dates = cap.build_dates(anchor, forecast_days)
        want_first = pd.Timestamp(dates[1])
        for sku in sku_list:
            first_pred = predictions[sku_list.index(sku)]["Day"].iloc[0]
            assert first_pred.normalize() == want_first.normalize()

    def test_po_applies_when_day_is_timestamp_normalized_to_dates(self, tmp_path):
        """Дата PO как Timestamp сопоставляется с тем же календарным днём, что и в `dates`."""
        dates = ["12/31/2025", "01/01/2026", "01/02/2026"]
        stocks = pd.DataFrame(
            {
                "SKU": ["S1"],
                "01/01/2026": [10.0],
                "01/02/2026": [10.0],
                "12/31/2025": [100.0],
            }
        )
        po = pd.DataFrame(
            {
                "Day": [pd.Timestamp("2026-01-01")],
                "SKU": ["S1"],
                "Qty": [50],
            }
        )
        po_path = tmp_path / "po.csv"
        po.to_csv(po_path, index=False)

        out = cap.include_purchase_orders(stocks.copy(), str(po_path), dates, ["S1"])

        assert out["01/01/2026"].iloc[0] == 60.0

    def test_po_applied_when_day_string_matches_dates(self, tmp_path):
        """Строка даты в том же формате, что `dates`, — поставка учитывается."""
        dates = ["12/31/2025", "01/01/2026", "01/02/2026"]
        stocks = pd.DataFrame(
            {
                "SKU": ["S1"],
                "01/01/2026": [10.0],
                "01/02/2026": [10.0],
                "12/31/2025": [100.0],
            }
        )
        po = pd.DataFrame(
            {
                "Day": ["01/01/2026"],
                "SKU": ["S1"],
                "Qty": [50],
            }
        )
        po_path = tmp_path / "po.csv"
        po.to_csv(po_path, index=False)

        out = cap.include_purchase_orders(stocks.copy(), str(po_path), dates, ["S1"])

        assert out["01/01/2026"].iloc[0] == 60.0

    def test_inventory_initial_stock_joined_by_sku_not_row_order(self, tmp_path):
        """Стартовый остаток берётся по колонке `SKU`, а не по порядку строк в CSV."""
        dates = ["12/31/2025", "01/01/2026", "01/02/2026", "01/03/2026"]
        predictions = [
            pd.DataFrame({"Predicted Sold Total": [-1.0, -2.0, -3.0]}),
            pd.DataFrame({"Predicted Sold Total": [-4.0, -5.0, -6.0]}),
        ]
        inv_path = tmp_path / "inv.csv"
        pd.DataFrame(
            {"SKU": ["B", "A"], "12/31/2025": [999.0, 1.0]}
        ).to_csv(inv_path, index=False)

        stocks = cap.calculate_stocks(predictions, dates, ["A", "B"], str(inv_path))

        assert stocks.loc[0, "SKU"] == "A"
        assert stocks.loc[0, "12/31/2025"] == 1.0
        assert stocks.loc[1, "12/31/2025"] == 999.0
