"""Тесты для get_product_abc_xyz_analysis (ABC/XYZ, repair_product).

Карта классов к `CALCULATION_ISSUES.md`: `TestPriority3IssueDivisionByZero` — деление на ноль в ABC/XYZ;
`TestPriority2Issues` — `sells_col`, неизменность `Day`, merge, CSV; `TestEnhancementRepairProductPriority1` —
краевые случаи `repair_product` (пустой fit, линейный тренд, регрессия без `Day`).

TDD: ожидаемое **корректное** поведение при нулевой суммарной марже и нулевом среднем продаж —
конечные доли ABC и коэффициент вариации XYZ без `inf`/`NaN`.
"""

import numpy as np
import pandas as pd
import pytest

import get_product_abc_xyz_analysis as m


def _sku_frame(n_days, sku, price, cost, sold_per_day, start="2025-01-01"):
    """Одна SKU: n_days строк со Status=1, одинаковые Price/Cost/Sold."""
    days = pd.date_range(start, periods=n_days, freq="D")
    return pd.DataFrame(
        {
            "Day": days,
            "SKU": sku,
            "Sold": sold_per_day,
            "Price": price,
            "Cost": cost,
            "Status": 1,
        }
    )


class TestPriority3IssueDivisionByZero:
    """Деление на ноль и нечисловые доли: конечные `Share` (ABC) и `Coeff_variation` (XYZ)."""

    def test_abc_share_finite_when_total_margin_zero(self):
        """ABC: при `total_margin == 0` доли конечны (не `inf`/`NaN` от деления)."""
        p1 = _sku_frame(3, "A", 10.0, 10.0, 1.0)
        p2 = _sku_frame(3, "B", 20.0, 20.0, 1.0)
        margin_table = m.get_abc_analysis([p1, p2])

        assert np.isfinite(margin_table["Share"]).all()

    def test_xyz_coeff_variation_finite_when_avg_sold_zero(self):
        """XYZ: при `Avg_sold == 0` коэффициент вариации конечен (определён без деления на ноль)."""
        df = _sku_frame(5, "Z", 10.0, 5.0, 0.0)
        df["Date_ordinal"] = df["Day"].map(pd.Timestamp.toordinal)
        stability = m.get_xyz_analysis([df])

        assert np.isfinite(stability["Coeff_variation"].iloc[0])


class TestPriority2Issues:
    """Колонка `sells_col`, неизменность `Day` после XYZ, дубликаты SKU при merge, валидация дат и отброс `Unnamed:*` в CSV."""

    def test_repair_product_writes_to_sells_col_not_hardcoded_sold(self):
        """Прогноз записывается в колонку `sells_col`, а не только в `Sold`."""
        days = pd.date_range("2025-01-01", periods=95, freq="D")
        product = pd.DataFrame(
            {
                "Day": days,
                "SKU": "X",
                "Qty": [3.0] * 90 + [0.0] * 5,
                "Price": 10.0,
                "Cost": 8.0,
                "Status": [1] * 90 + [0] * 5,
            }
        )
        product["Date_ordinal"] = product["Day"].map(pd.Timestamp.toordinal)

        out = m.repair_product(product, sells_col="Qty")

        assert out.loc[out["Status"] == 0, "Qty"].notna().all()
        assert (out.loc[out["Status"] == 0, "Qty"] >= 0).all()

    def test_get_xyz_analysis_does_not_mutate_day_column(self):
        """После XYZ колонка `Day` остаётся полной датой (не строкой YYYY-MM)."""
        p = _sku_frame(10, "M", 10.0, 5.0, 1.0)
        p["Date_ordinal"] = p["Day"].map(pd.Timestamp.toordinal)
        before = p["Day"].copy()
        m.get_xyz_analysis([p])
        assert p["Day"].dtype == before.dtype
        pd.testing.assert_series_equal(p["Day"], before, check_names=True)

    def test_merge_raises_when_duplicate_sku_in_margin_table(self):
        """Дубликат SKU в промежуточной таблице — явная ошибка, не «первая строка»."""
        margin = pd.DataFrame(
            {
                "SKU": ["A", "A"],
                "Margin": [10.0, 20.0],
                "Category": ["A", "B"],
            }
        )
        stability = pd.DataFrame(
            {
                "SKU": ["A"],
                "Coeff_variation": [5.0],
                "Category": ["X"],
            }
        )
        with pytest.raises(ValueError, match="duplicate"):
            m.merge_analysis_result(margin, stability, ["A"])

    def test_prepare_products_raises_on_invalid_day(self, tmp_path):
        """Битая дата в CSV — явная ошибка вместо тихого NaT."""
        pd.DataFrame(
            {
                "Day": ["2025-01-01", "not-a-date", "2025-01-03"],
                "SKU": ["S"] * 3,
                "Sold": [1.0, 1.0, 1.0],
                "Price": [10.0] * 3,
                "Cost": [8.0] * 3,
                "Status": [1] * 3,
            }
        ).to_csv(tmp_path / "bad.csv", index=False)

        with pytest.raises(ValueError, match="Invalid or missing Day"):
            m.prepare_products(tmp_path / "bad.csv")

    def test_merge_analysis_result_contains_both_skus_and_sorted_by_category(self):
        """Интеграция merge: две SKU, сортировка по категории при уникальных SKU."""
        p1 = _sku_frame(3, "A", 10.0, 5.0, 2.0)
        p2 = _sku_frame(3, "B", 10.0, 5.0, 1.0)
        margin = m.get_abc_analysis([p1, p2])
        stability = m.get_xyz_analysis([p1.copy(), p2.copy()])
        out = m.merge_analysis_result(margin, stability, ["B", "A"])

        assert set(out["SKU"]) == {"A", "B"}
        assert len(out) == 2
        assert list(out.columns) == ["SKU", "Margin", "Variation", "Category"]
        assert out["Category"].is_monotonic_increasing

    def test_prepare_products_strips_unnamed_columns_and_keeps_sku(self, tmp_path):
        """Служебные `Unnamed:*` отбрасываются; одна SKU с 90+ днями Status=1."""
        days = pd.date_range("2025-01-01", periods=91, freq="D")
        rows = [
            {
                "Unnamed: 0": i,
                "Day": d.strftime("%Y-%m-%d"),
                "SKU": "ONE",
                "Sold": 1.0,
                "Price": 10.0,
                "Cost": 8.0,
                "Status": 1,
            }
            for i, d in enumerate(days)
        ]
        pd.DataFrame(rows).to_csv(tmp_path / "in.csv", index=False)

        products, skus = m.prepare_products(tmp_path / "in.csv")

        assert skus == ["ONE"]
        assert "Unnamed: 0" not in products[0].columns
        assert len(products[0]) == 91


class TestEnhancementRepairProductPriority1:
    """Краевые сценарии `repair_product`: нет обучающих строк Status=1, фрейм без `Day`, линейное заполнение нулей по тренду."""

    def test_repair_product_no_crash_when_no_status_one_rows(self):
        """Нет строк со Status=1 — без `fit`, без падения sklearn."""
        product = pd.DataFrame(
            {
                "Day": pd.date_range("2025-01-01", periods=3, freq="D"),
                "SKU": "Z",
                "Sold": [0.0, 0.0, 0.0],
                "Price": 10.0,
                "Cost": 8.0,
                "Status": 0,
            }
        )
        product["Date_ordinal"] = product["Day"].map(pd.Timestamp.toordinal)
        out = m.repair_product(product)
        assert len(out) == 3

    def test_repair_product_handles_missing_status_without_indexing_error(self):
        """Регрессия: минимальный фрейм без `Day` — без ошибки индексации в `repair_product`."""
        product = pd.DataFrame(
            {
                "Status": [1, 1, 0],
                "Date_ordinal": [1, 2, 3],
                "Sold": [10.0, 12.0, 0.0],
            }
        )

        repaired = m.repair_product(product)

        assert len(repaired) == len(product)
        assert repaired.loc[repaired["Status"] == 0, "Sold"].notna().all()

    def test_repair_product_fills_status_zero_using_linear_trend(self):
        """Линейная регрессия по времени заполняет Status=0 (штатный сценарий `repair_product`)."""
        days = pd.date_range("2025-01-01", periods=95, freq="D")
        product = pd.DataFrame(
            {
                "Day": days,
                "SKU": "R",
                "Sold": [5.0] * 90 + [0.0] * 5,
                "Price": 10.0,
                "Cost": 8.0,
                "Status": [1] * 90 + [0] * 5,
            }
        )
        product["Date_ordinal"] = product["Day"].map(pd.Timestamp.toordinal)

        repaired = m.repair_product(product)

        assert repaired.loc[repaired["Status"] == 0, "Sold"].notna().all()
        assert (repaired.loc[repaired["Status"] == 0, "Sold"] >= 0).all()
