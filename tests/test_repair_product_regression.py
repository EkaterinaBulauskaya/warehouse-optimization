import pandas as pd

from projects.abc_xyz.get_product_abc_xyz_analysis import repair_product


def test_repair_product_handles_missing_status_without_indexing_error():
    product = pd.DataFrame(
        {
            "Status": [1, 1, 0],
            "Date_ordinal": [1, 2, 3],
            "Sold": [10.0, 12.0, 0.0],
        }
    )

    repaired = repair_product(product)

    assert len(repaired) == len(product)
    assert repaired.loc[repaired["Status"] == 0, "Sold"].notna().all()
