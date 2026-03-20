from __future__ import annotations

from datetime import datetime
import warnings

from src.market.services.hedonic_index import HedonicIndexService


def test_month_end__avoids_nanosecond_warning() -> None:
    service = HedonicIndexService.__new__(HedonicIndexService)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("error", UserWarning)
        value = service._month_end("2024-01")

    assert value == datetime(2024, 1, 31, 23, 59, 59, 999999)
    assert caught == []
